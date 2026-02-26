# Project Mode Guide

This guide explains how to use the multi-phase project functionality in SemanticForms.

## Overview

The project mode allows you to organize multiple questionnaires (CEDAR templates) across different project phases. This is useful for:
- Tracking progress through multiple stages of a project
- Organizing related questionnaires together
- Maintaining separate metadata for projects and their phases

## Configuration

### Enabling Project Mode

To enable project mode, add the `projects` section to your `config.yaml`:

```yaml
projects:
  enabled: true
  # Optional: CEDAR template for project metadata
  project_metadata_template:
    source: cedar
    api_key: your_api_key_here
    templateId: your_project_template_id_here
  # Define project phases and their associated templates
  phases:
    - name: "Phase 1: Initial Assessment"
      template:
        source: cedar
        api_key: your_api_key_here
        templateId: template_id_for_phase1
        title_predicate: title
    - name: "Phase 2: Development"
      template:
        source: cedar
        api_key: your_api_key_here
        templateId: template_id_for_phase2
        title_predicate: title
    - name: "Phase 3: Evaluation"
      template:
        source: cedar
        api_key: your_api_key_here
        templateId: template_id_for_phase3
        title_predicate: title
```

### Configuration Options

- `enabled`: Set to `true` to enable project mode
- `project_metadata_template` (optional): CEDAR template for project metadata collection
- `phases`: List of project phases, each with:
  - `name`: Display name for the phase
  - `template`: Template configuration (same format as main template config)

## Using Project Mode

### Creating a Project

1. Navigate to the application home page
2. When project mode is enabled, you'll be redirected to `/projects`
3. Click "New Project" or "Create First Project"
4. Fill in the project name and description (or use the CEDAR template if configured)
5. Click "Create Project"

### Viewing Projects

- All projects are listed on the `/projects` page
- Each project card shows:
  - Project name
  - Creation date
  - Description (if available)
  - Actions (View Details, Delete)

### Working with Project Phases

1. Click on a project to view its details
2. You'll see all configured phases
3. For each phase, you can:
   - View completed questionnaires
   - Add new questionnaires by clicking "Add Questionnaire"
   - Edit existing questionnaires

### Adding Questionnaires to a Phase

1. From the project detail page, click "Add Questionnaire" for the desired phase
2. Fill in the CEDAR template form
3. Click Save
4. You'll be redirected back to the project page

### Editing Questionnaires

1. From the project detail page, click "Edit" on an existing questionnaire
2. Modify the form fields
3. Click Save

### Deleting Projects

1. From the projects list, click "Delete" on a project
2. Confirm the deletion
3. **Warning**: This will delete all project data including all phase questionnaires

## Data Storage

### File Structure

When project mode is enabled, data is stored as follows:

```
data/
├── project_{project_id}/
│   ├── project_metadata.jsonld
│   ├── phase_Phase_1_Initial_Assessment_{response_id}.jsonld
│   ├── phase_Phase_2_Development_{response_id}.jsonld
│   └── phase_Phase_3_Evaluation_{response_id}.jsonld
```

### Project Metadata File

Each project has a `project_metadata.jsonld` file containing:
```json
{
  "@id": "http://localhost/project/{project_id}",
  "@type": "Project",
  "project_name": "My Project",
  "description": "Project description",
  "pav:createdOn": "2026-02-26T10:30:00+01:00",
  "created_by": "username"
}
```

### Phase Response Files

Each questionnaire response includes:
```json
{
  "@id": "http://localhost/project/{project_id}/phase/{response_id}",
  "project_id": "http://localhost/project/{project_id}",
  "project_phase": "Phase 1: Initial Assessment",
  "schema:isBasedOn": "template_id",
  "pav:createdOn": "2026-02-26T10:30:00+01:00",
  "pav:lastUpdatedOn": "2026-02-26T11:00:00+01:00",
  ...
}
```

## Legacy Mode (Non-Project)

When project mode is disabled (or not configured), the application works in legacy mode:
- Direct access to form instances at `/instances`
- No project organization
- Single template-based workflow
- Original behavior is preserved

## API Endpoints

### Project Mode Endpoints

- `GET /projects` - List all projects
- `GET /projects/create` - Create project form (GET) / Create project (POST)
- `GET /projects/{project_id}` - View project details
- `GET /projects/{project_id}/phase/{phase_index}/add` - Add phase questionnaire
- `GET /projects/{project_id}/phase/{phase_name}/response/{response_id}/edit` - Edit phase questionnaire
- `POST /api/projects/{project_id}/phase/{phase_name}/store` - Store phase response
- `PUT /api/projects/{project_id}/phase/{phase_name}/store` - Update phase response
- `POST /projects/{project_id}/delete` - Delete project

### Legacy Mode Endpoints

- `GET /` or `/instances` - List instances
- `GET /add` - Add new form
- `GET /instance/{id}` - View instance
- `GET /instance/{id}/edit` - Edit instance
- `POST /api/cedar/store` - Store/update instance

## Migration from Legacy to Project Mode

If you have existing instances and want to enable project mode:

1. Existing instances remain accessible at `/instances`
2. New projects can be created independently
3. Existing data is not automatically migrated
4. You can manually copy data if needed

## Troubleshooting

### Projects not appearing

- Check that `projects.enabled: true` in config.yaml
- Verify the storage folder is writable
- Check application logs for errors

### Phase questionnaires not saving

- Verify phase template configuration is correct
- Check API key validity for CEDAR templates
- Ensure network connectivity to CEDAR repository

### Cannot access legacy instances

- Navigate directly to `/instances` to view old data
- Legacy mode works alongside project mode
- Set `projects.enabled: false` to use only legacy mode

## Best Practices

1. **Phase Design**: Plan your phases before creating projects
2. **Naming**: Use descriptive project and phase names
3. **Backup**: Regularly backup your `data/` folder
4. **Testing**: Test template configuration before deployment
5. **Documentation**: Document your phase workflow for users

## Support

For issues or questions:
- Check the application logs
- Review the configuration file
- Consult the main README.md
- Report issues on GitHub
