import sys
import os
from dotenv import load_dotenv
from perplexity import Perplexity
from pdfextractor import extracttext
from readjsonld import read_jsonld_file
from jsonvalidation import validate_and_normalize_jsonld
from jsonvisualize import visualize_MainEntity, visualize_inputdata
from uploadjson import uploadjson
from rich import print as rprint

# Upload the input pdf file and extract text
# ! for future - add possibility to download pdf from doi
pdfname="s13048-022-00994-2.pdf"
text=extracttext(pdfname)

# Upload JSON-LD structures as template (empty structure) and example file
file_name_ex='example.jsonld'
json_example=read_jsonld_file(file_name_ex)

file_name_temp='template.jsonld'
json_template=read_jsonld_file(file_name_temp)

# Create the query
query_template=(f"Imagine you are an LLM agent tasked with filling in model metadata in a predefined, fixed JSON-LD structure.\
Your tasks are: \
Extract all required information from the provided published paper about the models {text}, including: \
Model names/identifiers Model types/architectures  \
Performance metrics with confidence intervals  \
Input features with full details (labels, types, categories, ranges) \
For all input features and categories you should find ID of ontology code and rfds:label as Preferred label from the ontology.\
Outcome variables with ID of ontology code and rfds:label as Preferred label from the ontology.\
Training and validation data details \
Clinical applicability, risks, mitigations, and use cases\
Metadata such as authorship, dates, contact, and references. \
Populate every single field in the provided JSON-LD template {json_template}, ensuring it matches exactly \
 the structure and field names of the example JSON-LD format, \
even if certain fields remain empty. \
The group Evaluation results1 should be just populated in JSON-LD file with null or empty fields. \
For all input features and categories, identify and use ontology URIs from validated, \
authoritative sources such as NCIT, SNOMED CT, ICD10M, LOINC, ROO, and others.\
Each ontology URI must be correct, well-formed, and verified. Perform ontology validation by: \
Confirming all ontology URIs exist and are resolvable in their respective sources. \
Ensuring ontology labels (rdfs:label) exactly match the preferred terms from the ontology. \
Checking case sensitivity and conforming to ontology standards. Detecting and resolving duplicate, \
fabricated, or unverified ontology codes. \
Applying corrections as needed, such as adjusting labels, removing invalid IDs, or substituting alternative valid ontology terms.\
Documenting validation results and corrections within metadata or accompanying documentation fields. \
Return the extracted ontology codes for input features and categories for validation by the user.\
Maintain full compliance with W3C JSON-LD 1.1 standard and FAIR data principles to facilitate semantic web usage, machine readability, \
and integration into knowledge bases and registries. Deliver the completed JSON-LD metadata, ready for production use, \
including notes on any ontology issues encountered and how they were addressed. \
As @id of the model use an universally unique identifier (UUID). \
As pav:createdOn use current date.\
Model information for the extraction is in the paper {text}. Example of JSON-LD is in the file {file_name_ex}. \
You should populate all structures from this file even if they are empty. \
Save thd complete JSON-LD structure in results. IMPORTANT: \
- Return ONLY valid JSON-LD \
- Do NOT include explanations and search result messages \
- Do NOT include markdown \
- Output must be a complete JSON object \
- Ensure the JSON is closed and valid. \ "
)

# Initialize the client (uses PERPLEXITY_API_KEY environment variable)
load_dotenv()  # reads .env in current directory. To write it - nano .env
api_key = os.getenv("PERPLEXITY_API_KEY")
client = Perplexity()

# Start the request
print("Querying Perplexity...")
result_parts = []

response = client.responses.create(
    #model="sonar",
    preset="pro-search",
    input=query_template,
    max_output_tokens=25000,
)

full_output=""

for item in response.output:
    if item.type=='message':
        for content in item.content:
            if content.type == "output_text":
                full_output += content.text

# Save full JSON-LD
file_name_output="output.jsonld"
with open(file_name_output, "w", encoding="utf-8") as f:
    f.write(full_output)

print(f"\n\nFull result saved to output.jsonld")

# Validate the content of json-ld file
normalized, errors, warnings = validate_and_normalize_jsonld(file_name_output)

# Visualize json-ld structure
# First - the general structure
visualize_MainEntity(file_name_output)

# second - input data with ontologies
visualize_inputdata(file_name_output)

# Upload to v3.fairmodels.org
url = "http://127.0.0.1:8000"
uploadjson(file_name_output, url)
