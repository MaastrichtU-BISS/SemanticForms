from operator import truediv
import flask
from flask import Flask, Response, request, redirect, url_for, session
from flask_cors import CORS
from jinja2 import Template
from pyparsing import Any
import yaml
import os
import requests
import uuid
import json
from rdflib import Graph
import logging
import sys
import datetime
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
from tzlocal import get_localzone
from persistance import FilePersistance

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.DEBUG)
# get local timezone    
local_tz = get_localzone()

load_dotenv()
app.secret_key = os.getenv("FLASK_SECRET_KEY")

keycloak_realm = os.getenv("KEYCLOAK_REALM")
keycloak_base_url = os.getenv("KEYCLOAK_BASE_URL")
keycloak_logout_url = f"{keycloak_base_url}/realms/{keycloak_realm}/protocol/openid-connect/logout"

oauth = OAuth(app)
oauth.register(
    name="keycloak",
    client_id=os.getenv("KEYCLOAK_CLIENT_ID"),
    client_secret=os.getenv("KEYCLOAK_CLIENT_SECRET"),
    authorize_url=f"{keycloak_base_url}/realms/{keycloak_realm}/protocol/openid-connect/auth",
    server_metadata_url=f"{keycloak_base_url}/realms/{keycloak_realm}/.well-known/openid-configuration",
    client_kwargs={"scope": "openid profile email"},
)

def loadConfig(pathString):
    """
    Load configuration file if found on path
    """
    if os.path.exists(pathString):
        with open(pathString) as f:
            config = yaml.safe_load(f)
            return config
    return { }

config = loadConfig("config.yaml")
if len(config)==0:
    config = loadConfig("../config.yaml")
if len(config)==0:
    logging.error("Could not find config.yaml file. System will exit")
    sys.exit(-1)

persistance = FilePersistance(folder_location=config['server']['storageFolder'],
                              title_uri=config['template']['title_predicate'],
                              base_url=config['template']['instance_base_url'] + "/instance")

def render_template(
    template_name_or_list: str | Template | list[str | Template],
    **context: Any
) -> str:
    """
    Override render_template to add user to the context
    """
    print(json.dumps(session.get("user"), indent=4))
    return flask.render_template(template_name_or_list, user=session.get("user"), **context)

@app.route("/")
def index():
    # Get search query from URL parameters
    search_query = request.args.get('search', '')
    
    # Get filter parameters
    filters = {}
    table_columns = config.get("tableColumns", [])
    
    for column in table_columns:
        filter_value = request.args.get(f"filter_{column['property']}", '')
        if filter_value:
            filters[column['property']] = filter_value
    
    # Get instances with properties extracted based on table columns
    instances = persistance.get_instances_with_properties(
        search_query if search_query.strip() else None, 
        table_columns
    )
    
    # Apply property filters
    if filters:
        filtered_instances = {}
        for instance_id, instance_data in instances.items():
            include_instance = True
            for prop, filter_value in filters.items():
                instance_value = instance_data.get('properties', {}).get(prop, '')
                if filter_value.lower() not in str(instance_value).lower():
                    include_instance = False
                    break
            if include_instance:
                filtered_instances[instance_id] = instance_data
        instances = filtered_instances
    
    # Get enhanced filter options with property analysis
    filter_options = persistance.get_enhanced_filter_options(table_columns)

    if ("application/json" in request.accept_mimetypes.best) | ("application/ld+json" in request.accept_mimetypes.best):
        return Response(json.dumps(instances), mimetype='application/json')
    
    if config["template"]["storage"]=="cedar":
        return render_template("index.html", 
                             instances=instances, 
                             template_id=config["template"]["templateId"], 
                             search_query=search_query,
                             table_columns=table_columns,
                             filters=filters,
                             filter_options=filter_options)
    else:
        return render_template("index.html", 
                             instances=instances, 
                             search_query=search_query,
                             table_columns=table_columns,
                             filters=filters,
                             filter_options=filter_options)

# Login page
@app.route("/login", methods=["GET", "POST"])
def login():
    redirect_uri = url_for("auth", _external=True, _scheme=os.getenv("APP_SCHEME", 'http'))
    return oauth.keycloak.authorize_redirect(redirect_uri)

# Auth callback
@app.route("/auth")
def auth():
    token = oauth.keycloak.authorize_access_token()
    session["user"] = oauth.keycloak.parse_id_token(token, nonce=token.get("nonce"))
    return redirect("/")

# Logout
@app.route("/logout", methods=["POST"])
def logout():
    session.pop("user", None)
    redirect_url = url_for('index', _external=True, _scheme=os.getenv("APP_SCHEME", 'http'))
    logout_url = f"{keycloak_logout_url}?post_logout_redirect_uri={redirect_url}&client_id={os.getenv('KEYCLOAK_CLIENT_ID')}"
    return redirect(logout_url)

@app.route("/add")
def cee():
    # Test authentication or send HTTP 401 error
    if not session.get("user"):
        return redirect("/login")
    return render_template("cee.html")

@app.route("/instance/<identifier>/edit")
def edit_cee(identifier: str):
    # Test authentication or to login page
    if not session.get("user"):
        return redirect("/login")
    
    if identifier:
        fileNameJson = persistance.get_instance(identifier)['filename']
        with open(fileNameJson, "r") as f:
            jsonData = json.load(f)

            infoData = {}
            
            infoData["isBasedOn"] = jsonData["schema:isBasedOn"]
            infoData["id"] = jsonData["@id"]
            infoData["createdOn"] = jsonData["pav:createdOn"]
            infoData["fileName"] = fileNameJson

            del jsonData["@id"]
            del jsonData["pav:createdOn"]
            del jsonData["schema:isBasedOn"]
        return render_template("cee.html", formData=json.dumps(jsonData), formInfo=json.dumps(infoData))
    
    return redirect("/", error="Could not load data")  

@app.route("/instance/<identifier>/delete")
def delete_instance(identifier: str):
    # Test authentication or to login page
    if not session.get("user"):
        return redirect("/login")
    
    if not persistance.instance_exists(identifier):
        return redirect("/", error=f"Could not find instance with id {identifier}")
    
    persistance.delete_instance(identifier)
    return redirect("/")

@app.route("/instance/<identifier>")
def showInstance(identifier: str):
    # # Test authentication or to login page
    # if not session.get("user"):
    #     return redirect("/login")
    
    filename = persistance.get_instance(identifier)['filename']
    with open(filename, "r") as f:
        jsonData = json.load(f)
    
    # if accept method is text/plain return n-triples
    if "application/n-triples" in request.accept_mimetypes.best:
        # Convert jsonData to n-triples
        g = Graph()
        g.parse(data=json.dumps(jsonData), format='json-ld')
        ntriples = g.serialize(format='nt')
        return Response(ntriples, mimetype='application/n-triples')
    
    if "application/json" in request.accept_mimetypes.best:
        return Response(json.dumps(jsonData), mimetype='application/json')
    
    if "application/ld+json" in request.accept_mimetypes.best:
        return Response(json.dumps(jsonData), mimetype='application/ld+json')
    
    if "application/rdf+xml" in request.accept_mimetypes.best:
        g = Graph()
        g.parse(data=json.dumps(jsonData), format='json-ld')
        rdfxml = g.serialize(format='xml')
        return Response(rdfxml, mimetype='application/rdf+xml')

    return render_template("instance.html", jsonData=jsonData, identifier=identifier)


@app.route("/api/cedar/template.json")
def template():
    """
    Retrieve cedar template from the main repository,
    and pass it to the embeddable editor in the front-end
    """
    template = get_template()
    return Response(json.dumps(template), mimetype='application/json')

def get_template():
    """
    Get template from cedar itself, or from a local json-ld file
    In config.yaml file for local file:
    ```
    template:
        source: file
        location: template.json
    ```

    In config.yaml for cedar:
    ```
    template:
        source: cedar
        api_key: <your_api_key>
        templateId: <your_template_uuid>
    ```
    """
    if config['template']['source'] == 'cedar':
        response=None
        if "api_key" in config['template']:
            headers = {
                "Authorization": f"apiKey {config['template']['api_key']}",
                "Content-Type": "application/json"
            }
            response = requests.get(f"https://repo.metadatacenter.org/templates/{config['template']['templateId']}", headers=headers)
        else:
            response = requests.get(f"https://open.metadatacenter.org/templates/https:%2F%2Frepo.metadatacenter.org%2Ftemplates%2F{config['template']['templateId']}")

        return json.loads(response.text)
    
    if config['template']['source'] == 'file':
        template = { }
        if os.path.exists(config['template']['location']):
            with open(config['template']['location']) as f:
                template = json.load(f)
        return template

@app.route("/api/cedar/store", methods=["POST", "PUT"])
def store():
    """
    Function to store the actual data generated using the cedar embeddable editor.
    """
    # TODO: Add authentication, as cedar is unaware of the user

    template = get_template()

    data_to_store = request.get_json()
    data_to_store_meta = data_to_store["metadata"]
    data_to_store_info = data_to_store["info"]

    if "id" in data_to_store_info:
        data_to_store_meta["@id"] = data_to_store_info["id"]
        data_to_store_meta["schema:isBasedOn"] = data_to_store_info["isBasedOn"]
        data_to_store_meta["pav:createdOn"] = data_to_store_info["createdOn"]
        data_to_store_meta["pav:lastUpdatedOn"] = datetime.datetime.now(local_tz).isoformat()
    else:
        data_to_store_meta["schema:isBasedOn"] = template['@id']
        data_to_store_meta["pav:createdOn"] = datetime.datetime.now(local_tz).isoformat()
        data_to_store_meta["pav:lastUpdatedOn"] = datetime.datetime.now(local_tz).isoformat()
    data_to_store["metadata"] = data_to_store_meta
    
    persistance.save_instance(data_to_store_meta)

    return {"message": "Hi there!"}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)