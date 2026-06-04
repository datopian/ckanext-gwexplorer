import json

import ckan.plugins.toolkit as tk


def gwexplorer_valid_spec(value):
    """Validate the stored Graphic Walker preset spec.

    The spec is posted by the view edit form as a JSON-encoded string holding a
    list of Graphic Walker chart objects (``IChart[]``). We only check that it
    is well-formed JSON and re-serialise it to a canonical, compact string so
    the persisted config stays stable. Empty values are handled upstream by
    ``ignore_empty`` and never reach this validator.
    """
    if value in (None, ""):
        return value

    if not isinstance(value, str):
        # Already-decoded structures (e.g. when called programmatically) are
        # accepted and normalised to a JSON string for storage.
        try:
            return json.dumps(value, separators=(",", ":"))
        except (TypeError, ValueError):
            raise tk.Invalid(tk._("Invalid Graphic Walker view specification"))

    try:
        parsed = json.loads(value)
    except (ValueError, TypeError):
        raise tk.Invalid(tk._("Graphic Walker view specification must be valid JSON"))

    return json.dumps(parsed, separators=(",", ":"))
