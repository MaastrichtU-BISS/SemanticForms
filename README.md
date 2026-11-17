# SemanticForms
A Cedar template implementation to fill in (and maintain) forms, based on the [Cedar Embeddable Editor](https://github.com/metadatacenter/cedar-embeddable-editor)

## Prerequisites
* Docker Engine (linux) / Docker for Windows / Docker for macOS

Additional prerequisites are needed for development:

* Python >= 3.8
* NodeJS v16 and NPM

## How to run
1. Clone or download this GitHub repository to your local PC
2. Open the downloaded/cloned contents locally in the terminal
3. Run `docker-compose up -d`
4. when the previous command is finished, open the following url: [http://localhost:5000](http://localhost:5000)

## Configure templates
By default a CEDAR template is given in [src/template.json](src/template.json). You can change this in the [src/config.yaml](src/config.yaml) file in:
```
template:
    source: cedar
    templateId: <location_of_cedar_json_ld_file>
```

If you want to connect to the CEDAR service API, it is possible to provide the following information in the [src/config.yaml](src/config.yaml) file:
```
template:
    source: cedar
    api_key: <your_api_key>
    templateId: <your_cedar_template_uuid>
```

Mind that the variable `api_key` is only needed for templates which are not available in Cedar's OpenView.

## Machine-readable access

All listing and detail pages support content negotiation, so the data can be crawled without
scraping HTML. Set the `Accept` header to one of `application/ld+json`, `application/json`,
`application/n-triples`, `text/turtle` or `application/rdf+xml`:

```bash
# All projects (project mode) or all instances (legacy mode); / redirects to /projects in project mode
curl -L -H "Accept: application/ld+json" http://localhost:5000/
curl -H "Accept: text/turtle" http://localhost:5000/projects
```

The landing page returns a `schema:Collection` whose `hasPart` lists the `@id` of every project
(with its name, creation date, page URL and the `@id`s of its phase responses) or instance. These
`@id`s are dereferenceable and support the same formats.

**Note:** the legacy `/` and `/instances` JSON response changed from an internal dictionary to this
JSON-LD collection.

## Project Mode (Multi-Phase Workflow)

SemanticForms now supports a **project mode** that allows organizing multiple questionnaires across different project phases. This is useful for tracking progress through multiple stages of work.

### Features

- Create projects with metadata
- Define multiple phases per project
- Each phase can have its own CEDAR template/questionnaire
- Track progress through all project phases
- Separate JSON-LD files for project metadata and each phase response

### Enabling Project Mode

Add the `projects` section to your `config.yaml`:

```yaml
projects:
  enabled: true
  phases:
    - name: "Phase 1: Initial Assessment"
      template:
        source: cedar
        api_key: your_api_key
        templateId: template_id_for_phase1
    - name: "Phase 2: Development"
      template:
        source: cedar
        api_key: your_api_key
        templateId: template_id_for_phase2
```

For detailed information on using project mode, see [PROJECT_MODE_GUIDE.md](PROJECT_MODE_GUIDE.md).

**Note**: Project mode is optional. If not configured, the application works in legacy mode with the original behavior.