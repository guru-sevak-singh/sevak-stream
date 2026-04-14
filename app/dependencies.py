from fastapi.templating import Jinja2Templates

'''
Here we describe all the dependency
1. templates which are used everywhere here.
'''
templates = Jinja2Templates(
    directory="app/templates"
)