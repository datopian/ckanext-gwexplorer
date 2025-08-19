# ckanext-gwexplorer
A CKAN data explorer built with [Graphic Walker](https://docs.kanaries.net/graphic-walker), which provides the ability to view raw dataset tables, explore their structure, and create interactive visualizations for deeper insights.

## Table View
<img width="1077" height="858" alt="Screenshot 2025-08-19 at 12 41 43 PM" src="https://github.com/user-attachments/assets/a0d8767d-a394-4bd4-a008-276c2c6c4af2" />

## Visualization 
<img width="1049" height="857" alt="Screenshot 2025-08-19 at 12 41 31 PM" src="https://github.com/user-attachments/assets/386fa51a-5b36-48f3-8b52-0d8e3e8dfa71" />

# Installation 

1. Activate your CKAN virtual environment, for example::
`. /usr/lib/ckan/default/bin/activate`

2. Install the ckanext-gwexplorer python package into your virtual environment
   `pip install -e git+https://github.com/datopian/ckanext-gwexplorer.git#egg=ckanext-gwexplorer`

3. Add `gwexplorer` to the ckan.plugins setting in your CKAN config file (by default the config file is located at /etc/ckan/default/ckan.ini)

4. Add `gwexplorer` in default views `ckan.views.default_views`
  ```
    ckan.views.default_views = image_view gwexplorer .. 
  ```


## Development 
It is built on [CKAN Graphic Walker](https://github.com/datopian/ckan-gw-explorer?tab=readme-ov-file#development). You can explore more in the repository if you need to modify it.

