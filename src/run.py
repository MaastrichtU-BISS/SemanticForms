from operator import truediv
from flask import Flask, Response, request, render_template, redirect
from flask_cors import CORS
import yaml
import os
import requests
import uuid
import json
from rdflib import Graph
import logging
import sys
import datetime
from tzlocal import get_localzone
from endpoint_service import SPARQLEndpoint

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.DEBUG)
# get local timezone    
local_tz = get_localzone() 

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

# Create storage folder
if not os.path.exists(config['server']['storageFolder']):
    os.makedirs(config['server']['storageFolder'])

sparqlEndpoint = SPARQLEndpoint(config["server"]["rdf_endpoint"], sparqlUpdateUrl=config["server"]["rdf_endpoint_update"])

@app.route("/")
def index():
    instances = sparqlEndpoint.list_instances()
    for idx, val in enumerate(instances):
        instances[idx]["instance"]["short"] = instances[idx]["instance"]["value"].replace(config["template"]["instance_base_url"] + "/", "")
    return render_template("index.html", instances=instances)

@app.route("/add")
def cee():
    return render_template("cee.html")

@app.route("/delete")
def delete_instance():
    identifier = request.args.get("uri")
    sparqlEndpoint.drop_instance(identifier)
    return redirect("/")

@app.route("/instance")
def showInstance():
    identifier = request.args.get("uri")
    properties = sparqlEndpoint.describe_instance(identifier)
    references = sparqlEndpoint.get_instance_links(identifier)
    return render_template("instance.html", properties=properties, references=references, instance_uri=identifier)

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
        headers = {
            "Authorization": f"apiKey {config['template']['apiKey']}",
            "Content-Type": "application/json"
        }

        response = requests.get(f"https://repo.metadatacenter.org/templates/{config['template']['templateId']}", headers=headers)
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
    template = get_template()
    session_id = uuid.uuid4()
    if request.method == "PUT":
        session_id = request.args.get("id")
    
    fileNameJson = os.path.join(config['server']['storageFolder'], f"{session_id}.jsonld")
    fileNameTurtle = os.path.join(config['server']['storageFolder'], f"{session_id}.ttl")

    data_to_store = request.get_json()
    data_to_store = data_to_store["metadata"]
    data_to_store["schema:isBasedOn"] = template['@id']
    data_to_store["pav:createdOn"] = datetime.datetime.now(local_tz).isoformat()
    data_to_store["@id"] = f"{config['template']['instance_base_url']}/{session_id}"

    with open(fileNameJson, "w") as f:
        json.dump(data_to_store, f, indent=4)
    
    g = Graph()
    g.parse(data=json.dumps(data_to_store), format='json-ld')
    g.serialize(destination=fileNameTurtle)
    
    turtleData = g.serialize(format='nt')
    sparqlEndpoint.store_instance(turtleData, data_to_store["@id"])

    return {"id": f"{session_id}", "message": "Hi there!"}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)