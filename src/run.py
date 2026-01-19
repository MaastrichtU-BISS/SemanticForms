from operator import truediv
from werkzeug.utils import secure_filename
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
# from authlib.integrations.flask_client import OAuth
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

# oauth = OAuth(app)
# oauth.register(
#     name="keycloak",
#     client_id=os.getenv("KEYCLOAK_CLIENT_ID"),
#     client_secret=os.getenv("KEYCLOAK_CLIENT_SECRET"),
#     authorize_url=f"{keycloak_base_url}/realms/{keycloak_realm}/protocol/openid-connect/auth",
#     server_metadata_url=f"{keycloak_base_url}/realms/{keycloak_realm}/.well-known/openid-configuration",
#     client_kwargs={"scope": "openid profile email"},
# )

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

@app.route("/debug/list-instances")
def debug_list_instances():
    items = persistance.get_instances_with_properties(None, config.get("tableColumns", []))
    return Response(json.dumps(items, indent=2), mimetype='application/json')

@app.route("/")
def index():
    # Get search query from URL parameters
    search_query = request.args.get('search', '')
    
    # Get sort parameters
    sort_by = request.args.get('sort', '')
    sort_order = request.args.get('order', 'asc')  # asc or desc
    
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
    
    # Apply sorting if requested
    if sort_by and table_columns:
        # Validate sort_by is in configured columns
        valid_properties = [col['property'] for col in table_columns]
        if sort_by in valid_properties:
            instances = dict(sorted(instances.items(), 
                key=lambda item: persistance.get_sortable_value(item[1], sort_by),
                reverse=(sort_order == 'desc')))
    
    # Get enhanced filter options with property analysis
    filter_options = persistance.get_enhanced_filter_options(table_columns)


    if ("application/json" in request.accept_mimetypes.best) | ("application/ld+json" in request.accept_mimetypes.best):
        return Response(json.dumps(instances), mimetype='application/json')
    
    # Add sort info to template context
    sort_info = {
        'sort_by': sort_by,
        'sort_order': sort_order
    }
    
    if config["template"]["storage"]=="cedar":
        return render_template("index.html", 
                             instances=instances,
                             template_id=config["template"]["templateId"], 
                             search_query=search_query,
                             table_columns=table_columns,
                             filters=filters,
                             filter_options=filter_options,
                             sort_info=sort_info)
    else:
        return render_template("index.html", 
                             instances=instances,
                             search_query=search_query,
                             table_columns=table_columns,
                             filters=filters,
                             filter_options=filter_options,
                             sort_info=sort_info)

# Login page
# @app.route("/login", methods=["GET", "POST"])
# def login():
#     redirect_uri = url_for("auth", _external=True, _scheme=os.getenv("APP_SCHEME", 'http'))
#     return oauth.keycloak.authorize_redirect(redirect_uri)
#
# # Auth callback
# @app.route("/auth")
# def auth():
#     token = oauth.keycloak.authorize_access_token()
#     session["user"] = oauth.keycloak.parse_id_token(token, nonce=token.get("nonce"))
#     return redirect("/")
#
# # Logout
# @app.route("/logout", methods=["POST"])
# def logout():
#     session.pop("user", None)
#     redirect_url = url_for('index', _external=True, _scheme=os.getenv("APP_SCHEME", 'http'))
#     logout_url = f"{keycloak_logout_url}?post_logout_redirect_uri={redirect_url}&client_id={os.getenv('KEYCLOAK_CLIENT_ID')}"
#     return redirect(logout_url)

# DEVELOPMENT: Mock routes
@app.route('/login', methods=["GET", "POST"])
def login():
    # Mock user session
    session['user'] = {
        'sub': 'dev-user-001',
        'email': 'dev@maastrichtuniversity.nl',
        'name': 'Developer',
        'preferred_username': 'developer'
    }
    return redirect('/')

@app.route('/logout', methods=["POST"])
def logout():
    session.clear()
    return redirect('/')

@app.route("/add")
def cee():
    # Test authentication or send HTTP 401 error
    # if not session.get("user"):
    #     return redirect("/login")
    #
    bioportal_key = config.get("bioportal", {}).get("api_key", "")
    # print(bioportal_key)
    return render_template("form.html", 
                         templateObject=get_template(),
                         bioportal_api_key=bioportal_key)

# helper: validate and (optionally) auto-fix uploaded JSON-LD
def validate_and_normalize_jsonld(data):
    """
    Validate the uploaded JSON-LD dict and normalize it so it fits the app expectations.
    Returns (normalized_data, errors, warnings).
    - errors (list): fatal problems -> upload should be rejected
    - warnings (list): non-fatal issues (we auto-fixed) -> show to user
    """
    errors = []
    warnings = []

    # Must be an object
    if not isinstance(data, dict):
        errors.append("Uploaded JSON must be an object (JSON-LD document).")
        return data, errors, warnings

    # Title predicate configured in config (optional but recommended)
    title_pred = config.get('template', {}).get('title')
    if title_pred:
        if title_pred not in data:
            errors.append(f"Missing title predicate: '{title_pred}'. The table needs this to show a title.")
    # schema:isBasedOn is expected by edit flow — try to fill from template if missing
    if not data.get("schema:isBasedOn"):
        try:
            tpl = get_template()
            tpl_id = tpl.get('@id') if isinstance(tpl, dict) else None
            if tpl_id:
                data["schema:isBasedOn"] = tpl_id
                warnings.append("Missing 'schema:isBasedOn' — set to current template @id.")
            else:
                errors.append("Missing 'schema:isBasedOn' and no template is available to set it from.")
        except Exception:
            errors.append("Missing 'schema:isBasedOn' and failed to fetch template.")

    # @id handling: if present, check base; if missing, generate
    base = config.get('template', {}).get('instance_base_url', '').rstrip('/')
    if '@id' in data:
        if base and not str(data['@id']).startswith(base):
            # This could be fatal depending on your app, we'll treat it as a warning and offer to rewrite
            warnings.append(f"@id does not start with configured instance_base_url ('{base}'). It may not be editable in the UI.")
            # Optionally we could rewrite it; here we leave it but warn
    else:
        # generate an @id consistent with base, or urn:uuid if no base
        if base:
            data['@id'] = f"{base}/{uuid.uuid4()}"
            warnings.append("No @id provided — generated one using instance_base_url.")
        else:
            data['@id'] = f"urn:uuid:{uuid.uuid4()}"
            warnings.append("No @id provided — generated a urn:uuid id.")

    # pav:createdOn: add if missing (not fatal)
    if 'pav:createdOn' not in data:
        data['pav:createdOn'] = datetime.datetime.now(local_tz).isoformat()
        warnings.append("No 'pav:createdOn' found — set to current timestamp.")

    return data, errors, warnings

# New upload route (GET shows form, POST handles file upload)
@app.route("/upload", methods=["GET", "POST"])
def upload_instance():
    # require login similar to other protected routes
    if not session.get("user"):
        return redirect("/login")

    if request.method == "GET":
        return render_template("upload.html")

    uploaded = request.files.get("instancefile")
    if not uploaded or uploaded.filename == "":
        return render_template("upload.html", errors=["No file selected"])

    filename = uploaded.filename
    if not filename.lower().endswith((".jsonld", ".json")):
        return render_template("upload.html", errors=["Only .jsonld or .json files are allowed"])

    try:
        data = json.load(uploaded.stream)
    except Exception as e:
        app.logger.warning("Upload: invalid JSON-LD file: %s", str(e))
        return render_template("upload.html", errors=[f"Invalid JSON: {str(e)}"])

    # base = config.get('template', {}).get('instance_base_url', '').rstrip('/')
    # if not base:
    #     new_id = f"urn:uuid:{uuid.uuid4()}"
    # else:
    #     if '@id' not in data or not str(data.get('@id')).startswith(base):
    #         new_id = f"{base}/{uuid.uuid4()}"
    #     else:
    #         new_id = data.get('@id')
    # data['@id'] = new_id
    #
    # if 'pav:createdOn' not in data:
    #     data['pav:createdOn'] = datetime.datetime.now(local_tz).isoformat()
    # Validate and normalize
    normalized, errors, warnings = validate_and_normalize_jsonld(data)

    # If there are fatal errors, show them and do not save
    if errors:
        return render_template("upload.html", errors=errors, warnings=warnings, formData=normalized)

    # Save file to storage folder with a uuid filename (scanner will pick it up)
    storage_folder = config['server']['storageFolder']
    os.makedirs(storage_folder, exist_ok=True)
    out_filename = f"{uuid.uuid4()}.jsonld"
    out_path = os.path.join(storage_folder, secure_filename(out_filename))

    # with open(out_path, "w", encoding="utf-8") as f:
    #     json.dump(normalized, f, indent=2, ensure_ascii=False)

    # app.logger.info("Uploaded instance saved to %s (uri=%s)", out_path, normalized.get('@id'))

    # Register with persistence so it appears immediately
    try:
        persistance.save_instance(normalized)
        app.logger.info("Uploaded instance saved to %s (uri=%s)", out_path, normalized.get('@id'))
    except Exception as e:
        # fallback: write to disk if persistance.save_instance is not available or fails
        app.logger.warning("persistance.save_instance failed, falling back to direct file write: %s", e)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(normalized, f, indent=2, ensure_ascii=False)
        # if possible, call save_instance again or trigger a rescan
        try:
            persistance.save_instance(normalized)
        except Exception:
            app.logger.warning("Indexing failed after fallback write")

    # Optionally render a success page with warnings; for simplicity redirect to index
    if warnings:
        # show warnings on index by rendering upload.html with success info instead of redirect,
        # or flash messages. Here we flash messages (requires template to render flashes)
        from flask import flash
        for w in warnings:
            flash(w, "warning")

    return redirect("/")

@app.route("/instance/<identifier>/edit")
def edit_cee(identifier: str):
    # Test authentication or to login page
    # if not session.get("user"):
    #     return redirect("/login")
    
    if identifier:
        print(f"Loading instance from file: {identifier}")
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
        
        bioportal_key = config.get("bioportal", {}).get("api_key", "")
        return render_template("form.html",
                               templateObject=get_template(),
                               formData=jsonData,
                               formInfo=infoData,
                               bioportal_api_key=bioportal_key)
    
    return redirect("/", error="Could not load data")  

@app.route("/instance/<identifier>/delete")
def delete_instance(identifier: str):
    # Test authentication or to login page
    # if not session.get("user"):
    #     return redirect("/login")
    
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
    print(filename)
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

    # Get template for rendering the instance view
    templateObject = get_template()
    
    return render_template("instance.html", 
                         jsonData=jsonData, 
                         identifier=identifier,
                         templateObject=templateObject)


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
            print("api_key")
            headers = {
                "Authorization": f"apiKey {config['template']['api_key']}",
                "Content-Type": "application/json"
            }
            response = requests.get(f"https://repo.metadatacenter.org/templates/{config['template']['templateId']}", headers=headers)
            url=f"https://repo.metadatacenter.org/templates/{config['template']['templateId']}"
            print(f"📋 Fetching from CEDAR repo: {url}")

        else:
            response = requests.get(f"https://open.metadatacenter.org/templates/https:%2F%2Frepo.metadatacenter.org%2Ftemplates%2F{config['template']['templateId']}")

        # Check for errors
        if response.status_code != 200:
            print(f"❌ Error {response.status_code}: {response.text}")
            return {"error": f"Failed to fetch template: {response.status_code}"}, response.status_code

        print(f"✅ Template loaded successfully")

        return json.loads(response.text)
    
    if config['template']['source'] == 'file':
        template = { }
        template_path = config['template']['location']
        
        # Try relative to current working directory first
        if not os.path.exists(template_path):
            # Try relative to this file's directory
            script_dir = os.path.dirname(os.path.abspath(__file__))
            template_path = os.path.join(script_dir, config['template']['location'])
        
        if os.path.exists(template_path):
            logging.info(f"Loading template from: {template_path}")
            with open(template_path, 'r') as f:
                template = json.load(f)
        else:
            logging.error(f"Template file not found at: {template_path}")
            logging.error(f"Current working directory: {os.getcwd()}")
            
        return template

@app.route("/api/cedar/store", methods=["POST", "PUT"])
def store():
    """
    Function to store the actual data generated using the cedar embeddable editor.
    """
    # TODO: Add authentication, as cedar is unaware of the user

    template = get_template()
    session_id = uuid.uuid4()
    if request.method == "PUT":
        session_id = request.args.get("id")
    
    fileNameJson = os.path.join(config['server']['storageFolder'], f"{session_id}.jsonld")
    print(fileNameJson)
    fileNameTurtle = os.path.join(config['server']['storageFolder'], f"{session_id}.ttl")

    data_to_store = request.get_json()
    data_to_store_meta = data_to_store["metadata"]
    fileNameJson = None
    target = data_to_store_meta
    
    if request.method == "POST":
        session_id = uuid.uuid4()
        print("new profile")
        print(f"Session id: {session_id}")

        fileNameJson = os.path.join(config['server']['storageFolder'], f"{session_id}.jsonld")
        target["schema:isBasedOn"] = template['@id']
        target["pav:createdOn"] = datetime.datetime.now(local_tz).isoformat()
        target["@id"] = f"{config['template']['instance_base_url']}/{session_id}"
    else:
        data_to_store_info = data_to_store["info"]
        fileNameJson = data_to_store_info['fileName']
        print("existing profile")
        target["@id"] = data_to_store_info["id"]
        target["schema:isBasedOn"] = data_to_store_info["isBasedOn"]
        target["pav:createdOn"] = data_to_store_info["createdOn"]
        target["pav:lastUpdatedOn"] = datetime.datetime.now(local_tz).isoformat()
    
    persistance.save_instance(data_to_store_meta)

    return {"message": "ok"}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)