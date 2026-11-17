from operator import truediv
import flask
from flask import Flask, Response, request, redirect, url_for, session, abort
from flask_cors import CORS
from jinja2 import Template
from pyparsing import Any
import yaml
import os
import requests
import uuid
import time
from urllib.parse import quote
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
# Do not send the session cookie on cross-site POSTs (mitigates CSRF on delete actions)
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

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

def accepts(mimetype: str) -> bool:
    """
    True if the best matching Accept mimetype of the request is the given type.
    Requests without an Accept header (best is None) are treated as HTML requests.
    """
    return mimetype in (request.accept_mimetypes.best or "")

def is_admin(user) -> bool:
    """
    True if the user is listed in projects.admins (by email, preferred_username or sub).
    """
    if not user:
        return False
    admins = config.get("projects", {}).get("admins", []) or []
    return any(user.get(key) in admins for key in ("email", "preferred_username", "sub") if user.get(key))

def can_manage_project(project) -> bool:
    """
    True if the logged-in user may edit or delete the given project (dict from persistance.get_project):
    the creator of the project or a configured admin. Projects without a recorded creator can only be
    managed by admins.
    """
    user = session.get("user")
    if not user:
        return False
    if is_admin(user):
        return True
    owner_sub = (project or {}).get("metadata", {}).get("created_by_sub")
    return owner_sub is not None and owner_sub == user.get("sub")

app.jinja_env.globals["can_manage_project"] = can_manage_project
app.jinja_env.globals["projects_enabled"] = config.get("projects", {}).get("enabled", False)

def render_template(
    template_name_or_list: str | Template | list[str | Template],
    **context: Any
) -> str:
    """
    Override render_template to add user to the context
    """
    return flask.render_template(template_name_or_list, user=session.get("user"), **context)

@app.errorhandler(403)
@app.errorhandler(404)
def handle_http_error(error):
    """
    Render client errors as a page with a way back (JSON for API calls).
    """
    if request.path.startswith("/api/"):
        return {"error": error.description}, error.code
    return render_template("error.html", error=error), error.code

@app.route("/")
def index():
    # Check if project mode is enabled
    if config.get("projects", {}).get("enabled", False):
        # Redirect to projects page
        return redirect("/projects")
    
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

    if (accepts("application/json")) | (accepts("application/ld+json")):
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

def safe_next_url(url):
    """
    Only allow same-site relative paths as post-login redirect targets (prevents open redirects).
    """
    if url and url.startswith("/") and not url.startswith("//") and "\\" not in url:
        return url
    return None

def redirect_to_login():
    """
    Redirect to the login page, remembering the current page to return to after login.
    """
    return redirect(url_for("login", next=request.full_path.rstrip("?")))

# Login page
@app.route("/login", methods=["GET", "POST"])
def login():
    next_url = safe_next_url(request.args.get("next"))
    if next_url:
        session["next_url"] = next_url
    else:
        session.pop("next_url", None)
    redirect_uri = url_for("auth", _external=True, _scheme=os.getenv("APP_SCHEME", 'http'))
    return oauth.keycloak.authorize_redirect(redirect_uri)

# Auth callback
@app.route("/auth")
def auth():
    token = oauth.keycloak.authorize_access_token()
    session["user"] = oauth.keycloak.parse_id_token(token, nonce=token.get("nonce"))
    return redirect(safe_next_url(session.pop("next_url", None)) or "/")

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
        return redirect_to_login()
    
    bioportal_key = config.get("bioportal", {}).get("api_key", "")
    return render_template("form.html", 
                         templateObject=get_template(),
                         bioportal_api_key=bioportal_key)

@app.route("/instance/<identifier>/edit")
def edit_cee(identifier: str):
    # Test authentication or to login page
    if not session.get("user"):
        return redirect_to_login()
    
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
    if not session.get("user"):
        return redirect_to_login()
    
    if not persistance.instance_exists(identifier):
        return redirect("/", error=f"Could not find instance with id {identifier}")
    
    persistance.delete_instance(identifier)
    return redirect("/")

@app.route("/instance/<identifier>")
def showInstance(identifier: str):
    
    filename = persistance.get_instance(identifier)['filename']
    with open(filename, "r") as f:
        jsonData = json.load(f)
    
    # if accept method is text/plain return n-triples
    if accepts("application/n-triples"):
        # Convert jsonData to n-triples
        g = Graph()
        g.parse(data=json.dumps(jsonData), format='json-ld')
        ntriples = g.serialize(format='nt')
        return Response(ntriples, mimetype='application/n-triples')
    
    if accepts("application/json"):
        return Response(json.dumps(jsonData), mimetype='application/json')
    
    if accepts("application/ld+json"):
        return Response(json.dumps(jsonData), mimetype='application/ld+json')
    
    if accepts("application/rdf+xml"):
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


# In-memory cache of CEDAR templates: {template_id: (fetched_at, template)}
_cedar_template_cache = {}

def fetch_cedar_template(template_id: str, api_key: str = None):
    """
    Fetch a CEDAR template (via the API with an api key, or via OpenView without), cached in memory
    for server.template_cache_seconds (default 600) so pages do not wait on CEDAR for every request.
    """
    ttl = config.get("server", {}).get("template_cache_seconds", 600)
    cached = _cedar_template_cache.get(template_id)
    if cached and time.time() - cached[0] < ttl:
        return cached[1]

    if api_key:
        headers = {
            "Authorization": f"apiKey {api_key}",
            "Content-Type": "application/json"
        }
        response = requests.get(f"https://repo.metadatacenter.org/templates/{template_id}", headers=headers)
    else:
        response = requests.get(f"https://open.metadatacenter.org/templates/https:%2F%2Frepo.metadatacenter.org%2Ftemplates%2F{template_id}")

    template = json.loads(response.text)
    # Only cache successful lookups (a template always has an @id)
    if isinstance(template, dict) and "@id" in template:
        _cedar_template_cache[template_id] = (time.time(), template)
    return template

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
        templateId: <your_template_uuid>
    ```
    API key can be specified in template config or at top level as 'api_key'
    """
    if config['template']['source'] == 'cedar':
        # Check for api_key in template config, then fall back to top-level api_key
        api_key = config['template'].get('api_key') or config.get('api_key')
        return fetch_cedar_template(config['template']['templateId'], api_key)
    
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
    if not session.get("user"):
        return {"error": "Unauthorized"}, 401

    template = get_template()
    session_id = uuid.uuid4()
    if request.method == "PUT":
        session_id = request.args.get("id")
    
    fileNameJson = os.path.join(config['server']['storageFolder'], f"{session_id}.jsonld")
    fileNameTurtle = os.path.join(config['server']['storageFolder'], f"{session_id}.ttl")

    data_to_store = request.get_json()
    data_to_store_meta = data_to_store["metadata"]
    fileNameJson = None
    target = data_to_store_meta
    
    if request.method == "POST":
        session_id = uuid.uuid4()
        print("new profile")

        fileNameJson = os.path.join(config['server']['storageFolder'], f"{session_id}.jsonld")
        target["schema:isBasedOn"] = template['@id']
        target["pav:createdOn"] = datetime.datetime.now(local_tz).isoformat()
        target["@id"] = f"{config['template']['instance_base_url']}/instance/{session_id}"
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

# ============================================
# Project Management Routes
# ============================================

@app.route("/projects")
def projects_list():
    """
    List all projects. This is the main page in project mode.
    """
    # Check if projects are enabled
    if not config.get("projects", {}).get("enabled", False):
        # If projects not enabled, redirect to standard index
        return redirect("/instances")
    
    projects = persistance.get_all_projects(config)
    
    # Sort projects by creation date (newest first)
    projects_sorted = dict(sorted(projects.items(), 
                                 key=lambda item: item[1].get('created_on', ''), 
                                 reverse=True))
    
    for project_id, project in projects_sorted.items():
        project["phases_started"] = count_started_phases(project_id)

    return render_template("projects.html",
                           projects=projects_sorted,
                           phase_count=len(config.get("projects", {}).get("phases", [])))

@app.route("/projects/create", methods=["GET", "POST"])
def create_project():
    """
    Create a new project with metadata.
    """
    # Test authentication
    if not session.get("user"):
        return redirect_to_login()
    
    if not config.get("projects", {}).get("enabled", False):
        return redirect("/")
    
    if request.method == "POST":
        project_name = request.form.get("project_name")
        if not project_name:
            return render_template("project_create.html", error="Project name is required")
        
        # Create basic project metadata
        project_metadata = {
            "project_name": project_name,
            "description": request.form.get("description", ""),
            "created_by": session.get("user", {}).get("name", "Unknown"),
            "created_by_sub": session.get("user", {}).get("sub")
        }
        
        project_id = persistance.create_project(project_name, project_metadata)
        return redirect(f"/projects/{project_id}")
    
    # GET request - show form
    # Check if there's a project metadata template configured
    template_object = None
    if "project_metadata_template" in config.get("projects", {}):
        template_object = get_template_by_config(config["projects"]["project_metadata_template"])
        # If template configured, use form.html with project-specific variables
        bioportal_key = config.get("bioportal", {}).get("api_key", "")
        return render_template("form.html",
                             templateObject=template_object,
                             formData=None,
                             formInfo=None,
                             bioportal_api_key=bioportal_key,
                             is_project_create=True)
    
    # No template configured, use simple form
    bioportal_key = config.get("bioportal", {}).get("api_key", "")
    return render_template("project_create.html", 
                         templateObject=None,
                         bioportal_api_key=bioportal_key)

@app.route("/api/projects/store", methods=["POST"])
def store_project_metadata():
    """
    API endpoint to store project metadata from template form.
    """
    # Test authentication
    if not session.get("user"):
        return {"error": "Unauthorized"}, 401
    
    if not config.get("projects", {}).get("enabled", False):
        return {"error": "Projects not enabled"}, 400
    
    data = request.get_json()
    metadata = data.get("metadata", {})
    
    # Add user info if available
    metadata["created_by"] = session["user"].get("name", "Unknown")
    metadata["created_by_sub"] = session["user"].get("sub")
    
    # Don't extract or pass project_name separately - it's stored within the CEDAR template data
    # The name will be extracted dynamically from fields like "project_name", "name", or "title"
    project_id = persistance.create_project(None, metadata)
    return {"message": "ok", "project_id": project_id}

@app.route("/instance/project/<project_id>")
def resolve_project_uri(project_id: str):
    """
    Make the project @id (<instance_base_url>/instance/project/<id>) dereferenceable.
    Clients keep their Accept header across the redirect, so RDF/JSON-LD negotiation still works.
    """
    if not persistance.project_exists(project_id):
        abort(404, description=f"Project {project_id} not found")
    return redirect(f"/projects/{project_id}", code=303)

@app.route("/instance/project/<project_id>/phase/<response_id>")
def resolve_phase_response_uri(project_id: str, response_id: str):
    """
    Make the phase response @id (<instance_base_url>/instance/project/<id>/phase/<rid>) dereferenceable.
    """
    try:
        response = persistance.get_project_phase_response(project_id, response_id)
    except Exception:
        abort(404, description=f"Response {response_id} not found in project {project_id}")
    phase = quote(response["phase_name"], safe="")
    return redirect(f"/projects/{project_id}/phase/{phase}/response/{response_id}", code=303)

@app.route("/projects/<project_id>/phase/<phase_name>/response/<response_id>")
def view_phase_response(project_id: str, phase_name: str, response_id: str):
    """
    Display a single phase response (read-only view).
    """
    try:
        response = persistance.get_project_phase_response(project_id, response_id)
        response_data = response["data"]
        
        # Get the phase configuration to retrieve the template
        phases = config.get("projects", {}).get("phases", [])
        phase_template = None
        for phase in phases:
            if phase.get("name") == phase_name:
                phase_template = get_template_by_config(phase.get("template", {}))
                break
        
        # If no template found, use default template
        if not phase_template:
            phase_template = get_template()
        
        # Handle different response formats
        if accepts("application/n-triples"):
            g = Graph()
            g.parse(data=json.dumps(response_data), format='json-ld')
            ntriples = g.serialize(format='nt')
            return Response(ntriples, mimetype='application/n-triples')
        
        if accepts("application/json"):
            return Response(json.dumps(response_data), mimetype='application/json')
        
        if accepts("application/ld+json"):
            return Response(json.dumps(response_data), mimetype='application/ld+json')
        
        if accepts("application/rdf+xml"):
            g = Graph()
            g.parse(data=json.dumps(response_data), format='json-ld')
            rdfxml = g.serialize(format='xml')
            return Response(rdfxml, mimetype='application/rdf+xml')
        
        # Render HTML view
        project = persistance.get_project(project_id, config)
        return render_template("phase_response.html",
                             jsonData=response_data,
                             templateObject=phase_template,
                             response_id=response_id,
                             project=project,
                             phase_name=phase_name)
    except Exception as e:
        app.logger.error(f"Error viewing phase response: {str(e)}")
        abort(404, description=f"The response {response_id} could not be found in this project.")

@app.route("/projects/<project_id>")
def project_detail(project_id: str):
    """
    Show project details and phases.
    Supports multiple output formats via content negotiation.
    """
    if not config.get("projects", {}).get("enabled", False):
        return redirect("/")
    
    try:
        project = persistance.get_project(project_id, config)
        project_metadata = project["metadata"]
        phases = config.get("projects", {}).get("phases", [])
        phase_responses = persistance.get_project_phase_responses(project_id)
        
        # Handle different response formats via content negotiation
        # For non-HTML formats, include both project metadata and references to phase responses
        if accepts("application/n-triples") or \
           accepts("application/json") or \
           accepts("application/ld+json") or \
           accepts("application/rdf+xml"):
            
            # Create comprehensive project data with references to phase responses
            comprehensive_data = {
                "@context": project_metadata.get("@context", {}),
                "@id": project_metadata.get("@id"),
                "@type": "Project",
                "project_metadata": project_metadata,
                "phases": []
            }
            
            # Add references to phase responses (not full content)
            for phase_name, responses in phase_responses.items():
                phase_data = {
                    "phase_name": phase_name,
                    "responses": [response["data"].get("@id") for response in responses if "@id" in response["data"]]
                }
                comprehensive_data["phases"].append(phase_data)
            
            # Return in requested format
            if accepts("application/n-triples"):
                g = Graph()
                g.parse(data=json.dumps(comprehensive_data), format='json-ld')
                ntriples = g.serialize(format='nt')
                return Response(ntriples, mimetype='application/n-triples')
            
            if accepts("application/json"):
                return Response(json.dumps(comprehensive_data, indent=2), mimetype='application/json')
            
            if accepts("application/ld+json"):
                return Response(json.dumps(comprehensive_data, indent=2), mimetype='application/ld+json')
            
            if accepts("application/rdf+xml"):
                g = Graph()
                g.parse(data=json.dumps(comprehensive_data), format='json-ld')
                rdfxml = g.serialize(format='xml')
                return Response(rdfxml, mimetype='application/rdf+xml')
        
        # Default: render HTML view
        for phase_name, responses in phase_responses.items():
            phase_config = get_phase_config(phase_name)
            for response in responses:
                response["title"] = get_response_title(phase_config, response["data"])
                response["created_by"] = response["data"].get("pav:createdBy", "")

        return render_template("project_detail.html", 
                             project=project,
                             project_template=get_project_metadata_template(),
                             phases=phases,
                             phase_responses=phase_responses)
    except Exception as e:
        logging.error(f"Error loading project {project_id}: {e}")
        abort(404, description=f"The project {project_id} could not be found.")

def get_response_title(phase_config, response_data) -> str:
    """
    Human readable title of a phase response, using the phase template's title_predicate
    (falls back to a 'Title'/'title' field). Returns an empty string if none is found.
    """
    template_config = (phase_config or {}).get("template", {})
    candidates = [template_config.get("title_predicate"), "Title", "title"]
    for predicate in [c for c in candidates if c]:
        value = persistance._extract_cedar_field_value(response_data, predicate)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""

def count_started_phases(project_id: str) -> int:
    """
    Number of configured phases of a project that have at least one response.
    """
    phase_names = {p.get("name") for p in config.get("projects", {}).get("phases", [])}
    try:
        responses = persistance.get_project_phase_responses(project_id)
    except Exception:
        return 0
    return len([name for name, items in responses.items() if items and name in phase_names])

PROJECT_INTERNAL_FIELDS = ["@id", "@type", "pav:createdOn", "pav:lastUpdatedOn", "created_by", "created_by_sub", "project_name", "description"]

def get_project_metadata_template():
    """
    Return the configured CEDAR template for project metadata, or None if projects use the simple form.
    """
    template_config = config.get("projects", {}).get("project_metadata_template")
    return get_template_by_config(template_config) if template_config else None

@app.route("/projects/<project_id>/edit")
def edit_project(project_id: str):
    """
    Edit the metadata of a project (only when a project metadata template is configured).
    """
    if not session.get("user"):
        return redirect_to_login()
    try:
        project = persistance.get_project(project_id, config)
    except Exception:
        abort(404, description=f"Project {project_id} not found")
    if not can_manage_project(project):
        abort(403, description="Only the project creator or an administrator can edit this project")
    template_object = get_project_metadata_template()
    if template_object is None:
        abort(404, description="Project metadata editing requires a project_metadata_template")

    metadata = project["metadata"]
    form_data = {k: v for k, v in metadata.items() if k not in PROJECT_INTERNAL_FIELDS}
    info_data = {"id": metadata.get("@id"), "createdOn": metadata.get("pav:createdOn")}
    bioportal_key = config.get("bioportal", {}).get("api_key", "")
    return render_template("form.html",
                           templateObject=template_object,
                           formData=form_data,
                           formInfo=info_data,
                           bioportal_api_key=bioportal_key,
                           project_id=project_id,
                           project=project,
                           is_project_edit=True)

@app.route("/api/projects/<project_id>/store", methods=["PUT"])
def update_project(project_id: str):
    """
    API endpoint to update the metadata of an existing project.
    """
    if not session.get("user"):
        return {"error": "Unauthorized"}, 401
    try:
        project = persistance.get_project(project_id, config)
    except Exception:
        return {"error": f"Project {project_id} not found"}, 404
    if not can_manage_project(project):
        return {"error": "Forbidden"}, 403

    metadata = request.get_json().get("metadata", {})
    persistance.update_project_metadata(project_id, metadata)
    return {"message": "ok", "project_id": project_id}

@app.route("/projects/<project_id>/phase/<int:phase_index>/add")
def add_phase_response(project_id: str, phase_index: int):
    """
    Add a questionnaire response for a specific project phase.
    """
    # Test authentication
    if not session.get("user"):
        return redirect_to_login()
    
    if not config.get("projects", {}).get("enabled", False):
        return redirect("/")
    
    # Get phase configuration
    phases = config.get("projects", {}).get("phases", [])
    if phase_index >= len(phases):
        return redirect(f"/projects/{project_id}")
    
    if not persistance.project_exists(project_id):
        abort(404, description=f"Project {project_id} not found")

    phase = phases[phase_index]
    phase_template = get_template_by_config(phase.get("template", {}))
    
    bioportal_key = config.get("bioportal", {}).get("api_key", "")
    return render_template("form.html",
                         templateObject=phase_template,
                         bioportal_api_key=bioportal_key,
                         project_id=project_id,
                         project=persistance.get_project(project_id, config),
                         phase_name=phase.get("name"),
                         phase_index=phase_index,
                         is_project_mode=True)

@app.route("/projects/<project_id>/phase/<phase_name>/response/<response_id>/edit")
def edit_phase_response(project_id: str, phase_name: str, response_id: str):
    """
    Edit an existing phase response.
    """
    # Test authentication
    if not session.get("user"):
        return redirect_to_login()
    
    if not config.get("projects", {}).get("enabled", False):
        return redirect("/")
    
    # Load the response
    phase_responses = persistance.get_project_phase_responses(project_id)
    response_data = None
    response_file = None
    
    for phase, responses in phase_responses.items():
        for resp in responses:
            if resp["id"] == response_id:
                response_data = resp["data"]
                response_file = resp["filename"]
                break
        if response_data:
            break
    
    if not response_data:
        return redirect(f"/projects/{project_id}")
    
    # Find phase index to get template
    phases = config.get("projects", {}).get("phases", [])
    phase_index = 0
    phase_template = None
    
    for idx, phase in enumerate(phases):
        if phase.get("name") == phase_name:
            phase_index = idx
            phase_template = get_template_by_config(phase.get("template", {}))
            break
    
    if not phase_template:
        return redirect(f"/projects/{project_id}")
    
    # Prepare form info
    infoData = {
        "isBasedOn": response_data.get("schema:isBasedOn", ""),
        "id": response_data.get("@id", ""),
        "createdOn": response_data.get("pav:createdOn", ""),
        "fileName": response_file,
        "project_id": project_id,
        "phase_name": phase_name,
        "phase_index": phase_index
    }
    
    # Remove metadata fields for form
    form_data = response_data.copy()
    for key in ["@id", "pav:createdOn", "schema:isBasedOn", "project_phase", "project_id", "pav:lastUpdatedOn",
                "pav:createdBy", "pav:lastUpdatedBy"]:
        form_data.pop(key, None)
    
    bioportal_key = config.get("bioportal", {}).get("api_key", "")
    return render_template("form.html",
                         templateObject=phase_template,
                         formData=form_data,
                         formInfo=infoData,
                         bioportal_api_key=bioportal_key,
                         project_id=project_id,
                         project=persistance.get_project(project_id, config),
                         phase_name=phase_name,
                         phase_index=phase_index,
                         is_project_mode=True)

@app.route("/api/projects/<project_id>/phase/<phase_name>/store", methods=["POST", "PUT"])
def store_project_phase(project_id, phase_name):
    """
    Store a questionnaire response for a project phase.
    """
    if not session.get("user"):
        return {"error": "Unauthorized"}, 401

    if not persistance.project_exists(project_id):
        return {"error": f"Project {project_id} not found"}, 404

    phase_config = get_phase_config(phase_name)
    if phase_config is None:
        return {"error": f"Phase {phase_name} is not configured"}, 404

    data_to_store = request.get_json()
    data_to_store_meta = data_to_store["metadata"]
    phase_template = get_template_by_config(phase_config.get("template", {}))
    
    if request.method == "POST":
        # New response
        if phase_template and "@id" in phase_template:
            data_to_store_meta["schema:isBasedOn"] = phase_template["@id"]
        
        response_id = persistance.save_project_phase_response(
            project_id, 
            phase_name, 
            data_to_store_meta,
            user_name=session["user"].get("name")
        )
        return {"message": "ok", "response_id": response_id}
    else:
        # Update existing response
        data_to_store_info = data_to_store.get("info", {})
        if "id" in data_to_store_info:
            data_to_store_meta["@id"] = data_to_store_info["id"]
        if "isBasedOn" in data_to_store_info:
            data_to_store_meta["schema:isBasedOn"] = data_to_store_info["isBasedOn"]
        if "createdOn" in data_to_store_info:
            data_to_store_meta["pav:createdOn"] = data_to_store_info["createdOn"]
        
        response_id = persistance.save_project_phase_response(
            project_id,
            phase_name,
            data_to_store_meta,
            user_name=session["user"].get("name")
        )
        return {"message": "ok", "response_id": response_id}

@app.route("/projects/<project_id>/phase/<phase_name>/response/<response_id>/delete", methods=["POST"])
def delete_phase_response(project_id: str, phase_name: str, response_id: str):
    """
    Delete a single phase response. Allowed for the project creator and admins.
    """
    if not session.get("user"):
        return redirect_to_login()

    try:
        project = persistance.get_project(project_id, config)
        persistance.get_project_phase_response(project_id, response_id)
    except Exception:
        abort(404, description=f"Response {response_id} not found in project {project_id}")
    if not can_manage_project(project):
        abort(403, description="Only the project creator or an administrator can delete responses")

    persistance.delete_project_phase_response(project_id, response_id)
    return redirect(f"/projects/{project_id}")

@app.route("/projects/<project_id>/delete", methods=["POST"])
def delete_project(project_id: str):
    """
    Delete a project and all its data.
    """
    # Test authentication
    if not session.get("user"):
        return redirect_to_login()

    try:
        project = persistance.get_project(project_id, config)
    except Exception:
        abort(404, description=f"Project {project_id} not found")
    if not can_manage_project(project):
        abort(403, description="Only the project creator or an administrator can delete this project")

    persistance.delete_project(project_id)
    return redirect("/projects")

@app.route("/instances")
def instances_list():
    """
    Show instances list (legacy mode or when projects are disabled).
    This is the original index behavior.
    """
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

    if (accepts("application/json")) | (accepts("application/ld+json")):
        return Response(json.dumps(instances), mimetype='application/json')
    
    # Add sort info to template context
    sort_info = {
        'sort_by': sort_by,
        'sort_order': sort_order
    }
    
    is_project_mode = config.get("projects", {}).get("enabled", False)
    
    if config["template"]["storage"]=="cedar":
        return render_template("index.html", 
                             instances=instances, 
                             template_id=config["template"]["templateId"], 
                             search_query=search_query,
                             table_columns=table_columns,
                             filters=filters,
                             filter_options=filter_options,
                             sort_info=sort_info,
                             is_project_mode=is_project_mode)
    else:
        return render_template("index.html", 
                             instances=instances, 
                             search_query=search_query,
                             table_columns=table_columns,
                             filters=filters,
                             filter_options=filter_options,
                             sort_info=sort_info,
                             is_project_mode=is_project_mode)

def get_phase_config(phase_name):
    """
    Return the configuration of the phase with the given name, or None if not configured.
    """
    for phase in config.get("projects", {}).get("phases", []):
        if phase.get("name") == phase_name:
            return phase
    return None

def get_template_by_config(template_config):
    """
    Get template based on configuration object.
    Similar to get_template() but accepts a config dict.
    API key priority: template_config > top-level config
    """
    if not template_config:
        return get_template()  # Fall back to default
    
    if template_config.get('source') == 'cedar':
        # Check for api_key in template_config, then fall back to top-level api_key
        api_key = template_config.get('api_key') or config.get('api_key')
        return fetch_cedar_template(template_config['templateId'], api_key)
    
    if template_config.get('source') == 'file':
        template = {}
        template_path = template_config['location']
        
        if not os.path.exists(template_path):
            script_dir = os.path.dirname(os.path.abspath(__file__))
            template_path = os.path.join(script_dir, template_config['location'])
        
        if os.path.exists(template_path):
            with open(template_path, 'r') as f:
                template = json.load(f)
        
        return template
    
    return get_template()  # Fall back to default

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)