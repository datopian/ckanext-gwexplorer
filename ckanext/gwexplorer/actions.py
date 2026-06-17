import logging
from typing import Dict, List, Any
import json

import ckan.plugins.toolkit as tk
from psycopg2.extensions import adapt
from pygwalker.services.data_parsers import get_parser
from pygwalker.data_parsers.database_parser import Connector
from pygwalker.utils.encode import DataFrameEncoder

COLUMNS_TO_EXCLUDE = ["_id", "id", "_full_text"]
DEFAULT_POOL_SIZE = 15
DEFAULT_MAX_OVERFLOW = 100
DEFAULT_POOL_RECYCLE = 3600

# Field-name fragments used to auto-detect geographic coordinate columns.
LATITUDE_HINTS = ("latitude", "lat", "y")
LONGITUDE_HINTS = ("longitude", "long", "lng", "lon", "x")

log = logging.getLogger(__name__)


class DSLQueryError(Exception):
    """Custom exception for DSL query errors."""
    pass


def _reset_gw_dsl_parser() -> None:
    """Recreate the gw_dsl_parser WASM singleton.

    gw_dsl_parser instantiates its WASM module into one shared wasmtime
    Store on every query and never releases the instances, so after 10k
    queries the store hits wasmtime's instance limit and every query
    fails ("resource limit exceeded: instance count too high") until the
    singleton and its store are recreated.
    """
    from gw_dsl_parser import core as gw_dsl_core

    gw_dsl_core.dsl_to_wasm = gw_dsl_core.DslToSqlWasm()


class DatabaseConnectionError(Exception):
    """Custom exception for database connection errors."""

    pass


class DSLService:
    """
    Service class for handling DSL (Domain Specific Language) operations.

    This class encapsulates all database connection, metadata retrieval,
    and data querying functionality for CKAN datastore table.
    """

    def __init__(self):
        """Initialize the DSL service."""
        self.columns_to_exclude = COLUMNS_TO_EXCLUDE

    def _create_error_response(
        self, field: str, message: str = "field required"
    ) -> Dict[str, Any]:
        """
        Create a standardized error response.

        Args:
            field: The field that caused the error
            message: Error message

        Returns:
            Standardized error response dictionary
        """
        return {
            "detail": [
                {
                    "loc": ["query", field],
                    "msg": message,
                    "type": "value_error.missing",
                }
            ]
        }

    def _get_database_connection_params(self) -> Dict[str, Any]:
        """
        Get database connection parameters from configuration.

        Returns:
            Dictionary containing connection parameters
        """
        return {
            "pool_size": tk.config.get("ckanext.odn.dsl.pool_size", DEFAULT_POOL_SIZE),
            "max_overflow": tk.config.get(
                "ckanext.odn.dsl.max_overflow", DEFAULT_MAX_OVERFLOW
            ),
            "pool_recycle": tk.config.get(
                "ckanext.odn.dsl.pool_recycle", DEFAULT_POOL_RECYCLE
            ),
            "echo": tk.config.get("ckanext.odn.dsl.echo", False),
            "echo_pool": tk.config.get("ckanext.odn.dsl.echo_pool", False),
        }

    def _get_table_parser(self, table_name: str) -> Any:
        """
        Create and return a table parser for the given table name.

        Args:
            table_name: Name of the table to parse

        Returns:
            Table parser object

        Raises:
            DatabaseConnectionError: If connection to database fails
        """
        try:
            read_url = tk.config.get("ckan.datastore.read_url", "")
            if not read_url:
                raise DatabaseConnectionError("Database read URL not configured")

            conn = Connector(
                read_url,
                f'select * from "{adapt(table_name).adapted}"',
                engine_params=self._get_database_connection_params(),
            )

            return get_parser(
                conn, infer_string_to_date=False, infer_number_to_dimension=False
            )
        except Exception as e:
            log.error(f"Failed to create table parser for {table_name}: {e}")
            raise DatabaseConnectionError(f"Database connection failed: {e}")

    def _get_name_title_map(self, table_name: str) -> Dict[str, str]:
        """
        Get mapping of field names to their display titles.

        Args:
            table_name: Name of the table

        Returns:
            Dictionary mapping field IDs to display names
        """
        try:
            result = tk.get_action("datastore_search")(
                {"ignore_auth": True}, {"resource_id": table_name, "limit": 0}
            )

            fields = result.get("fields", [])
            name_map = {}

            for field in fields:
                field_id = field["id"]
                if field_id not in self.columns_to_exclude:
                    label = field.get("info", {}).get("label", field_id)
                    name_map[field_id] = f"{label}"

            return name_map

        except Exception as e:
            log.error(f"Error fetching name-title mapping for {table_name}: {e}")
            return {}

    def get_table_metadata(
        self, table_name: str, sort: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get metadata for a table including field information.

        Args:
            table_name: Name of the table
            sort: Whether to sort fields by name

        Returns:
            List of field metadata dictionaries
        """
        try:
            table_parser = self._get_table_parser(table_name)
            name_title_map = self._get_name_title_map(table_name)

            result = table_parser.raw_fields
            filtered_result = [
                {**field, "name": name_title_map.get(field["fid"], field["fid"])}
                for field in result
                if field["fid"] not in self.columns_to_exclude
            ]

            if sort:
                filtered_result = sorted(filtered_result, key=lambda x: x["name"])

            return filtered_result

        except Exception as e:
            log.error(f"Error fetching table metadata for {table_name}: {e}")
            return []

    def get_data_from_payload(
        self, table_name: str, payload: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Get data from table using DSL payload.

        Args:
            table_name: Name of the table
            payload: DSL query payload

        Returns:
            List of data rows

        Raises:
            DSLQueryError: If query execution fails
        """
        try:
            table_parser = self._get_table_parser(table_name)
            try:
                result = table_parser.get_datas_by_payload(payload)
            except Exception as e:
                if "instance count too high" not in str(e):
                    raise
                log.warning(
                    "gw_dsl_parser WASM store exhausted, resetting and retrying"
                )
                _reset_gw_dsl_parser()
                result = table_parser.get_datas_by_payload(payload)

            filtered_response = [
                {
                    key: value
                    for key, value in row.items()
                    if key not in self.columns_to_exclude
                }
                for row in result
            ]

            return json.loads(json.dumps(filtered_response, cls=DataFrameEncoder))

        except Exception as e:
            log.error(f"Error executing DSL query for {table_name}: {e}")
            raise DSLQueryError(f"Query execution failed: {e}")

    def show_metadata(self, resource_id: str, sort: bool = False) -> Dict[str, Any]:
        """
        Retrieve metadata for a table by its ID.

        Args:
            resource_id: Resource ID
            sort: Whether to sort fields by name

        Returns:
            Dictionary containing table metadata
        """
        if not resource_id:
            return self._create_error_response("resourceID")

        try:
            fields_meta = self.get_table_metadata(resource_id, sort)

            return {
                "success": True,
                "schema": fields_meta,
                "name": resource_id,
                "resource_id": resource_id,
                "message": "",
            }

        except Exception as e:
            log.error(f"Error in show_metadata for resource {resource_id}: {e}")
            return {
                "success": False,
                "schema": [],
                "name": resource_id,
                "resource_id": resource_id,
                "message": f"Error fetching metadata: {e}",
            }

    def query_data(self, resource_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Query data from a table using DSL.

        Args:
            resource_id: Resource ID
            payload: DSL query payload

        Returns:
            Dictionary containing query results
        """
        if not resource_id:
            return self._create_error_response("resourceID")

        if not payload:
            return self._create_error_response("payload", "payload field required")

        try:
            data = self.get_data_from_payload(resource_id, payload)

            return {
                "success": True,
                "data": data,
                "message": "",
            }

        except DSLQueryError as e:
            return {
                "success": False,
                "data": None,
                "message": str(e),
            }
        except Exception as e:
            log.error(f"Unexpected error in query_data for resource {resource_id}: {e}")
            return {
                "success": False,
                "data": None,
                "message": f"Unexpected error: {e}",
            }


def _field_ref(field: Dict[str, Any], as_measure: bool = False) -> Dict[str, Any]:
    """Build a Graphic Walker encoding field reference from table metadata."""
    ref = {
        "fid": field["fid"],
        "name": field.get("name", field["fid"]),
        "semanticType": field.get("semanticType", "nominal"),
        "analyticType": field.get("analyticType", "dimension"),
    }
    if as_measure:
        ref["analyticType"] = "measure"
        ref["aggName"] = "sum"
    return ref


def _looks_like(name: str, hints) -> bool:
    name = (name or "").strip().lower()
    return any(name == h or name.startswith(h) for h in hints)


def _find_geo_pair(fields):
    """Return (lat_field, lon_field) if the columns look like coordinates."""
    lat = lon = None
    for f in fields:
        if f.get("semanticType") != "quantitative":
            continue
        key = f.get("fid", "") or f.get("name", "")
        if lat is None and _looks_like(key, ("latitude", "lat")):
            lat = f
        elif lon is None and _looks_like(key, ("longitude", "long", "lng", "lon")):
            lon = f
    return (lat, lon) if (lat and lon) else (None, None)


def build_default_charts(fields: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Generate sensible default Graphic Walker chart spec(s) for a dataset.

    Returns a list of *partial* chart specs (``PartialChart[]``). The client
    runs each through Graphic Walker's ``fillChart`` to produce a complete,
    valid ``IChart`` — so we only need to express the meaningful choices here:
    which fields go on which channel, the geom, and the coordinate system.

    Heuristic (first match wins; a geographic chart is always added when
    coordinate columns are present):
    - lat/lon columns        -> geographic point map
    - temporal + measure     -> line chart over time
    - dimension + measure    -> aggregated bar chart
    - two quantitative cols   -> scatter plot
    - otherwise              -> bar of the first dimension by record count
    """
    if not fields:
        return []

    # Full field palette (everything is available in the editor regardless of
    # what the default chart places on a channel).
    palette = {
        "dimensions": [
            _field_ref(f) for f in fields if f.get("analyticType") == "dimension"
        ],
        "measures": [
            _field_ref(f, as_measure=True)
            for f in fields
            if f.get("analyticType") == "measure"
        ],
    }

    lat, lon = _find_geo_pair(fields)
    # Coordinate columns are placed on the map; exclude them from the pools used
    # to pick a statistical chart so we don't, e.g., scatter latitude vs longitude.
    geo_fids = {f["fid"] for f in (lat, lon) if f}
    selectable = [f for f in fields if f.get("fid") not in geo_fids]

    dimensions = [f for f in selectable if f.get("analyticType") == "dimension"]
    measures = [f for f in selectable if f.get("analyticType") == "measure"]
    temporal = [f for f in selectable if f.get("semanticType") == "temporal"]

    def chart(name, geoms, encodings, coord="generic", aggregated=True):
        return {
            "name": name,
            "encodings": {**palette, **encodings},
            "config": {
                "defaultAggregated": aggregated,
                "geoms": geoms,
                "coordSystem": coord,
            },
        }

    charts: List[Dict[str, Any]] = []

    if lat and lon:
        charts.append(
            chart(
                "Map",
                ["poi"],
                {
                    "latitude": [_field_ref(lat, as_measure=True)],
                    "longitude": [_field_ref(lon, as_measure=True)],
                },
                coord="geographic",
                aggregated=False,
            )
        )

    if temporal and measures:
        charts.append(
            chart(
                "Trend",
                ["line"],
                {
                    "columns": [_field_ref(temporal[0])],
                    "rows": [_field_ref(measures[0], as_measure=True)],
                },
            )
        )
    elif dimensions and measures:
        charts.append(
            chart(
                "Summary",
                ["bar"],
                {
                    "columns": [_field_ref(dimensions[0])],
                    "rows": [_field_ref(measures[0], as_measure=True)],
                },
            )
        )
    elif len(measures) >= 2:
        charts.append(
            chart(
                "Scatter",
                ["point"],
                {
                    "columns": [_field_ref(measures[0])],
                    "rows": [_field_ref(measures[1])],
                },
                aggregated=False,
            )
        )
    elif not charts and dimensions:
        # Nothing numeric to aggregate: fall back to a record count per category.
        charts.append(
            chart(
                "Count",
                ["bar"],
                {
                    "columns": [_field_ref(dimensions[0])],
                    "rows": [
                        {
                            "fid": "gw_count_fid",
                            "name": "Row count",
                            "semanticType": "quantitative",
                            "analyticType": "measure",
                            "aggName": "count",
                            "computed": True,
                            "expression": {"op": "one", "params": [], "as": "gw_count_fid"},
                        }
                    ],
                },
            )
        )

    return charts


# Global service instance
_dsl_service = DSLService()


@tk.side_effect_free
def show_dsl_metadata(
    context: Dict[str, Any], data_dict: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Retrieve metadata for a resource by its ID.

    Args:
        context: CKAN context
        data_dict: Dictionary containing request data

    Returns:
        Dictionary containing resource metadata
    """
    resource_id = data_dict.get("resourceID")
    if not resource_id:
        return tk.abort(400, "resourceID field is required")
    
    
    tk.check_access("resource_show", context, {"id": resource_id})


    sort = data_dict.get("sort", "false").lower() == "true"

    return _dsl_service.show_metadata(resource_id, sort)


def dsl_query_data(
    context: Dict[str, Any], data_dict: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Query data from a database using DSL.

    Args:
        context: CKAN context
        data_dict: Dictionary containing request data

    Returns:
        Dictionary containing query results
    """


    resource_id = data_dict.get("resourceID")
    tk.check_access("resource_show", context, {"id": resource_id})

    payload = data_dict.get("payload")

    return _dsl_service.query_data(resource_id, payload)


def gwexplorer_default_spec(
    context: Dict[str, Any], data_dict: Dict[str, Any]
) -> Dict[str, Any]:
    """Suggest default Graphic Walker chart(s) for a resource based on its schema.

    Used when a resource view has no publisher preset: the explorer boots with
    these auto-generated charts (geo / line / bar / scatter) chosen from the
    field types. Returns ``PartialChart[]`` which the client normalises via
    ``fillChart``.

    Args:
        context: CKAN context
        data_dict: Must contain ``resourceID``

    Returns:
        Dictionary with ``success`` and a ``spec`` list of partial charts.
    """
    resource_id = data_dict.get("resourceID")
    if not resource_id:
        return tk.abort(400, "resourceID field is required")

    tk.check_access("resource_show", context, {"id": resource_id})

    try:
        fields = _dsl_service.get_table_metadata(resource_id, sort=False)
        return {
            "success": True,
            "spec": build_default_charts(fields),
            "resource_id": resource_id,
            "message": "",
        }
    except Exception as e:
        log.error(f"Error building default spec for resource {resource_id}: {e}")
        return {
            "success": False,
            "spec": [],
            "resource_id": resource_id,
            "message": f"Error building default spec: {e}",
        }
