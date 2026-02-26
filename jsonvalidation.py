import json
import uuid
import datetime
from tzlocal import get_localzone

# def validate_jsonld(jsonfile):
#
#     with open("output.jsonld", "w", encoding="utf-8") as f:
#         f.read()
#
#     required_fields = ["@context", "@type", "name"]
#     return all(field in f for field in required_fields)


def validate_and_normalize_jsonld(jsonfile):
    """
    Validate the uploaded JSON-LD dict and normalize it so it fits the app expectations.
    Returns (normalized_data, errors, warnings).
    - errors (list): fatal problems -> upload should be rejected
    - warnings (list): non-fatal issues (we auto-fixed) -> show to user
    """
    errors = []
    warnings = []

    # get local timezone
    local_tz = get_localzone()

    with open(jsonfile, "r") as f:
        data = json.load(f)


    # Must be an object
    if not isinstance(data, dict):
        errors.append("Uploaded JSON must be an object (JSON-LD document).")
        return data, errors, warnings

    # Title predicate configured in config (optional but recommended)
    title_pred = data.get('title')
    if title_pred:
        if title_pred not in data:
            errors.append(f"Missing title predicate: '{title_pred}'. The table needs this to show a title.")
    # schema:isBasedOn is expected by edit flow — try to fill from template if missing
    if not data.get("schema:isBasedOn"):
        try:
            tpl = data
            tpl_id = tpl.get('@id') if isinstance(tpl, dict) else None
            if tpl_id:
                data["schema:isBasedOn"] = tpl_id
                warnings.append("Missing 'schema:isBasedOn' — set to current template @id.")
            else:
                errors.append("Missing 'schema:isBasedOn' and no template is available to set it from.")
        except Exception:
            errors.append("Missing 'schema:isBasedOn' and failed to fetch template.")

    # @id handling: if present, check base; if missing, generate
    base = data.get('instance_base_url', '').rstrip('/')
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