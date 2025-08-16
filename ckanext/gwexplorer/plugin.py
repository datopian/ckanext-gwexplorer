import ckan.plugins as plugins
import ckan.plugins.toolkit as tk
import ckanext.gwexplorer.actions as actions


class GwexplorerPlugin(plugins.SingletonPlugin):
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.IActions)
    plugins.implements(plugins.IResourceView, inherit=True)
    
    # IConfigurer
    def update_config(self, config_):
        tk.add_template_directory(config_, "templates")
        tk.add_public_directory(config_, "public")
        tk.add_resource("assets", "gwexplorer")

    # IActions
    def get_actions(self):
        return {
            "show_dsl_metadata": actions.show_dsl_metadata,
            "dsl_query_data": actions.dsl_query_data,
        }

    def can_view(self, data_dict):
        resource = data_dict['resource']
        if (resource.get('datastore_active') or
                '_datastore_only_resource' in resource.get('url', '')):
            return True
        resource_format = resource.get('format', None)
        if resource_format:
            return resource_format.lower() in ['csv', 'xls', 'xlsx', 'tsv']
        else:
            return False
        

    def info(self):
        return {
            'name': 'gwexplorer',
            'title': 'Data Explorer',
            'requires_datastore': True,
            'default_title': tk._('Data Explorer'),
        }
    
    def get_helpers(self):
        return {}

    def view_template(self, context, data_dict):
        return 'gwexplorer.html'

    
