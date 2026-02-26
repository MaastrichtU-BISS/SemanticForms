import os, json, uuid, datetime

class Persistance:
    def __init__(self):
        print("Initializing persistance")

class FilePersistance(Persistance):
    def __init__(self, folder_location: str, title_uri: str, base_url='http://localhost/instance'):
        Persistance.__init__(self)
        self.__folder_location = folder_location
        self.__title_uri = title_uri
        self.__base_url = base_url
        self.__cached_items = { }
        self.__create_folder_if_not_exists()
        self.__scan_folder(action=self.__parse_jsonld_file)
    
    def __create_folder_if_not_exists(self):
        """
        Create the persistance folder if it does not exist.
        """
        if not os.path.exists(self.__folder_location):
            os.makedirs(self.__folder_location)
    
    def __scan_folder(self, action):
        """
        Loop over folders and detect files which are .jsonld files. In that specific case, execute the passed function
        """
        self.__cached_items = { }
        for root, dirs, files in os.walk(self.__folder_location, topdown=True):
            for myFile in files:
                if myFile.endswith(".jsonld"):
                    action(filename=os.path.join(root, myFile))
    
    def __find_title_recursively(self, metadata, uri_tree):
        """
        Find title by searching through JSON-LD structure.
        Enhanced to handle complex nested structures like CEDAR templates.
        Now uses unified property extraction logic.
        """
        # First, try the original recursive search approach using context
        try:
            predicate = uri_tree[0]  # Don't modify the original list
            for key in metadata.get("@context", {}):
                value = metadata["@context"][key]
                if value == predicate:
                    titleTag = key
                    if len(uri_tree) > 1:
                        return self.__find_title_recursively(metadata[titleTag], uri_tree[1:])
                    else:
                        found_value = self.__extract_value_from_structure(metadata.get(titleTag))
                        if found_value:
                            return found_value
        except (KeyError, IndexError, TypeError):
            pass
        
        # Enhanced search: Look for common title patterns in CEDAR JSON-LD
        title_patterns = [
            # Direct patterns
            "title", "name", "label", "rdfs:label", "schema:name", "dct:title",
            # CEDAR nested patterns - look for "General Model Information" -> "Title"
            "General Model Information.Title",
            # Other nested patterns
            "metadata.title", "metadata.name",
        ]
        
        for pattern in title_patterns:
            # Use direct nested property extraction to avoid recursion
            if '.' in pattern:
                title = self.__extract_nested_property_value(metadata, pattern)
            else:
                # Direct property lookup
                if pattern in metadata:
                    title = self.__extract_value_from_structure(metadata[pattern])
                else:
                    title = None
            
            if title and title != "No title found":
                return title
                    
        return "No title found"

    def __extract_searchable_content(self, metadata):
        """
        Extract all searchable text content from JSON-LD metadata.
        This includes values from fields that contain @value properties.
        Uses unified value extraction for consistency.
        """
        searchable_text = []
        
        def extract_values_recursively(obj):
            """
            Recursively extract searchable values from nested JSON-LD structure.
            """
            if isinstance(obj, dict):
                if "@value" in obj and obj["@value"] is not None:
                    # Extract the actual value from @value fields
                    searchable_text.append(str(obj["@value"]))
                else:
                    # Recursively process nested objects, skipping metadata fields
                    for key, value in obj.items():
                        if not self.__is_metadata_field(key):
                            extract_values_recursively(value)
            elif isinstance(obj, list):
                for item in obj:
                    extract_values_recursively(item)
            elif isinstance(obj, (str, int, float)) and obj is not None:
                # Direct values that aren't wrapped in @value
                searchable_text.append(str(obj))
        
        extract_values_recursively(metadata)
        return " ".join(searchable_text).lower()  # Convert to lowercase for case-insensitive search
    
    def __is_metadata_field(self, field_name):
        """
        Check if a field name represents metadata that should be excluded from search content.
        Centralizes the metadata field detection logic.
        """
        metadata_prefixes = ["@", "pav:", "schema:isBasedOn"]
        return any(field_name.startswith(prefix) for prefix in metadata_prefixes)
                    

    
    def __parse_jsonld_file(self, filename: str):
        """
        Read JSON-LD object from filename, and parse the title and identifier of the object.
        input:
            - filename: the path of the file to parse
        """
        try:
            with open(filename, 'r') as f:
                metadata = json.load(f)
                
                # Extract ID - handle different URL formats
                full_id = metadata.get("@id", "")
                if not full_id:
                    print(f"Warning: No @id found in {filename}, skipping")
                    return
                
                # Try to extract ID from URL
                # Handle both "http://localhost/instance/ID" and "http://localhost/ID"
                id = full_id
                if self.__base_url in full_id:
                    id = full_id.replace(self.__base_url + "/", "")
                else:
                    # Fallback: extract everything after the last /
                    id = full_id.split("/")[-1]
                
                title_found = self.__find_title_recursively(metadata, self.__title_uri.split("|"))
                
                # Extract searchable content from all fields
                searchable_content = self.__extract_searchable_content(metadata)
                
                # Check if pav:createdOn exists
                created_on = metadata.get('pav:createdOn', None)
                if not created_on:
                    print(f"Warning: No pav:createdOn found in {filename}, using empty string")
                    created_on = ""
                
                # Store complete metadata for property extraction
                self.__cached_items[id] = {
                    "title": title_found,
                    "filename": filename,
                    "time": created_on,
                    "searchable_content": searchable_content,
                    "metadata": metadata
                }
                
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON in {filename}: {e}")
        except KeyError as e:
            print(f"Missing required field in {filename}: {e}")
        except Exception as e:
            print(f"Error processing {filename}: {e}")
    
    def instance_exists(self, id: str) -> bool:
        """
        Check if an instance exists in the persistance folder.
        input:
            - id: the identifier of the instance to check
            output:
                - True if the instance exists, False otherwise
        """
        return id in self.__cached_items
    
    def get_instance(self, id: str):
        """
        Get an instance from the persistance folder.
        input:
            - id: the identifier of the instance to get
            
            output:
                - a dictionary of the instance
        """
        if id in self.__cached_items:
            return self.__cached_items[id]
        else:
            raise Exception(f"Could not find instance with id {id}")

    def get_instances_with_properties(self, search_query=None, table_columns=None):
        """
        List all instances with extracted properties for table columns.
        If search_query is provided, filter instances by title and content.
        If table_columns is provided, extract those properties from each instance.

        input:
            - search_query: optional search string to filter instances
            - table_columns: optional list of column configurations
        output:
            - a dictionary of instances with extracted properties
        """
        base_instances = self.get_instances(search_query)
        
        if not table_columns:
            return base_instances
        
        enhanced_instances = {}
        for instance_id, instance_data in base_instances.items():
            enhanced_data = instance_data.copy()
            enhanced_data['properties'] = {}
            
            # Extract each configured property using unified method
            for column in table_columns:
                property_name = column['property']
                property_value = self.__extract_unified_property_value(instance_data['metadata'], property_name)
                enhanced_data['properties'][property_name] = property_value
            
            enhanced_instances[instance_id] = enhanced_data
        
        return enhanced_instances

    def __extract_property_value(self, metadata, property_name):
        """
        Extract a specific property value from JSON-LD metadata.
        Now delegates to unified extraction method for consistency.
        
        input:
            - metadata: the JSON-LD metadata object
            - property_name: the property to extract (supports dot notation for nested properties)
        output:
            - the property value as a string, or empty string if not found
        """
        return self.__extract_unified_property_value(metadata, property_name)
    
    def __extract_unified_property_value(self, metadata, property_name):
        """
        Unified method to extract any property value from JSON-LD metadata.
        Supports nested properties using dot notation and handles all JSON-LD structures.
        This consolidates the logic from multiple redundant methods.
        
        input:
            - metadata: the JSON-LD metadata object
            - property_name: the property to extract (supports dot notation for nested properties)
        output:
            - the property value as a string, or empty string if not found
        """
        if not property_name or not metadata:
            return ""
        
        # Handle nested property paths (e.g., "metadata.project", "details.team.lead")
        if '.' in property_name:
            return self.__extract_nested_property_value(metadata, property_name)
        
        # First try direct property access
        if property_name in metadata:
            value = self.__extract_value_from_structure(metadata[property_name])
            if value:
                return value
        
        # Try to find through context mapping
        context = metadata.get("@context", {})
        for key, uri in context.items():
            if key == property_name and key in metadata:
                value = self.__extract_value_from_structure(metadata[key])
                if value:
                    return value
        
        # Special cases for common properties
        if property_name == "title":
            # Use direct title search without recursion - just look for common title fields
            title_fields = ["title", "name", "label", "rdfs:label", "schema:name", "dct:title"]
            for field in title_fields:
                if field in metadata:
                    value = self.__extract_value_from_structure(metadata[field])
                    if value:
                        return value
            return ""
        elif property_name in ["creation_date", "date_created"]:
            created_on = metadata.get("pav:createdOn", "")
            return self.__extract_value_from_structure(created_on) if created_on else ""
        elif property_name in ["updated_date", "date_updated"]:
            updated_on = metadata.get("pav:lastUpdatedOn", "")
            return self.__extract_value_from_structure(updated_on) if updated_on else ""
        
        return ""
    
    def __extract_nested_property_value(self, metadata, property_path):
        """
        Extract a nested property value using dot notation path.
        Enhanced to handle arrays and complex JSON-LD structures.
        
        input:
            - metadata: the JSON-LD metadata object
            - property_path: dot-separated path (e.g., "metadata.project", "details.team.lead")
        output:
            - the property value as a string, or empty string if not found
        """
        if not property_path or not metadata:
            return ""
            
        path_parts = property_path.split('.')
        current = metadata
        
        # Navigate through the nested structure
        for part in path_parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return ""
        
        # Extract value using unified extraction logic
        return self.__extract_value_from_structure(current)
    
    def __extract_value_from_structure(self, current):
        """
        Extract a meaningful value from various JSON-LD structures.
        Handles arrays, @value objects, direct values, and complex nested structures.
        This is the core method that handles all value extraction consistently.
        
        input:
            - current: the structure to extract value from
        output:
            - the extracted value as a string, or empty string if not found
        """
        if current is None:
            return ""
        elif isinstance(current, list):
            # Handle arrays - extract from first non-null item
            for item in current:
                if item is not None:
                    extracted = self.__extract_value_from_structure(item)
                    if extracted:
                        return extracted
            return ""
        elif isinstance(current, dict) and "@value" in current:
            # Handle @value JSON-LD structure
            value = current["@value"]
            return str(value) if value is not None else ""
        elif isinstance(current, (str, int, float)):
            # Handle direct primitive values
            return str(current)
        elif isinstance(current, dict):
            # Handle complex dict structures - look for meaningful content
            # Try common value fields in order of preference
            value_fields = ["@value", "value", "name", "title", "label", "rdfs:label"]
            for value_key in value_fields:
                if value_key in current:
                    extracted = self.__extract_value_from_structure(current[value_key])
                    if extracted:
                        return extracted
            
            # If no standard value field found and dict has only one key, use its value
            if len(current) == 1:
                key, val = next(iter(current.items()))
                if not self.__is_metadata_field(key):  # Avoid metadata fields
                    extracted = self.__extract_value_from_structure(val)
                    if extracted:
                        return extracted
        
        return ""

    def get_unique_property_values(self, property_name, table_columns=None):
        """
        Get all unique values for a specific property across all instances.
        Used for generating dropdown filter options.
        Enhanced to detect categorical vs non-categorical data.
        
        input:
            - property_name: the property to get unique values for
            - table_columns: optional table columns configuration
        output:
            - a list of unique property values
        """
        unique_values = set()
        
        for instance_id, instance_data in self.__cached_items.items():
            value = self.__extract_unified_property_value(instance_data['metadata'], property_name)
            if value and value.strip():
                unique_values.add(value)
        
        return sorted(list(unique_values))
    
    def analyze_property_characteristics(self, property_name):
        """
        Analyze a property to determine its characteristics for better filtering.
        This helps identify categorical vs continuous data, date fields, etc.
        
        input:
            - property_name: the property to analyze
        output:
            - dictionary with property characteristics
        """
        values = []
        unique_values = set()
        
        for instance_id, instance_data in self.__cached_items.items():
            value = self.__extract_unified_property_value(instance_data['metadata'], property_name)
            if value and value.strip():
                values.append(value)
                unique_values.add(value)
        
        total_count = len(values)
        unique_count = len(unique_values)
        
        if total_count == 0:
            return {
                'type': 'empty',
                'unique_values': [],
                'unique_count': 0,
                'total_count': 0,
                'is_categorical': False,
                'is_date': False,
                'filter_type': 'text'
            }
        
        # Determine if this looks like categorical data
        uniqueness_ratio = unique_count / total_count if total_count > 0 else 0
        
        # Check if values look like dates
        is_date_field = self._is_date_property(property_name, list(unique_values))
        
        # Check if values look categorical (limited unique values relative to total)
        is_categorical = (
            unique_count <= 15 and  # Not too many unique values
            (uniqueness_ratio <= 0.7 or unique_count <= 10) and  # Low uniqueness ratio or very few unique values
            not is_date_field and  # Not a date field
            not self._is_numeric_property(list(unique_values))  # Not numeric
        )
        
        # Determine filter type
        if is_categorical:
            filter_type = 'dropdown'
        elif is_date_field:
            filter_type = 'date'
        elif self._is_numeric_property(list(unique_values)):
            filter_type = 'range' if unique_count > 10 else 'dropdown'
        else:
            filter_type = 'text'
        
        return {
            'type': 'categorical' if is_categorical else 'continuous',
            'unique_values': sorted(list(unique_values)),
            'unique_count': unique_count,
            'total_count': total_count,
            'uniqueness_ratio': uniqueness_ratio,
            'is_categorical': is_categorical,
            'is_date': is_date_field,
            'is_numeric': self._is_numeric_property(list(unique_values)),
            'filter_type': filter_type
        }
    
    def _is_date_property(self, property_name, values):
        """
        Check if a property appears to contain date values.
        """
        import re
        
        # Check property name for date indicators - be more specific to avoid false positives
        property_lower = property_name.lower()
        
        # Specific date field patterns that are more likely to be dates
        date_field_patterns = [
            'creation_date', 'created_date', 'date_created',
            'updated_date', 'date_updated', 'last_updated', 
            'timestamp', 'created_on', 'updated_on',
            'date', 'time'
        ]
        
        # Check for exact matches or patterns that end with date indicators
        is_date_by_name = False
        for pattern in date_field_patterns:
            if (pattern == property_lower or 
                property_lower.endswith('_' + pattern) or 
                property_lower.endswith('.' + pattern) or
                property_lower.startswith(pattern + '_') or
                property_lower.startswith(pattern + '.')):
                is_date_by_name = True
                break
        
        # Also check for simple standalone words but be more restrictive
        simple_date_words = ['date', 'time', 'timestamp']
        if any(word == property_lower.split('.')[-1] for word in simple_date_words):
            is_date_by_name = True
        
        # If property name suggests it's not a date field, check values more thoroughly
        if not is_date_by_name:
            # Check value formats for date patterns
            date_patterns = [
                r'^\d{4}-\d{2}-\d{2}$',  # YYYY-MM-DD
                r'^\d{2}/\d{2}/\d{4}$',  # MM/DD/YYYY  
                r'^\d{4}/\d{2}/\d{2}$',  # YYYY/MM/DD
                r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}',  # ISO datetime
            ]
            
            if len(values) == 0:
                return False
            
            matching_values = 0
            for value in values[:5]:  # Check first 5 values
                if any(re.match(pattern, str(value)) for pattern in date_patterns):
                    matching_values += 1
            
            return matching_values / min(len(values), 5) > 0.8  # Require 80% match
        
        # If property name suggests it's a date field, also check values to confirm
        if is_date_by_name and len(values) > 0:
            # Check if values actually look like dates
            date_patterns = [
                r'\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
                r'\d{2}/\d{2}/\d{4}',  # MM/DD/YYYY
                r'\d{4}/\d{2}/\d{2}',  # YYYY/MM/DD
                r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}',  # ISO datetime
            ]
            
            matching_values = 0
            for value in values[:5]:
                if any(re.search(pattern, str(value)) for pattern in date_patterns):
                    matching_values += 1
            
            # If name suggests date but values don't match, it's probably not a date
            if matching_values == 0 and len(values) > 0:
                return False
        
        return is_date_by_name
    
    def _is_numeric_property(self, values):
        """
        Check if a property appears to contain numeric values.
        """
        if len(values) == 0:
            return False
        
        numeric_count = 0
        for value in values:
            try:
                float(str(value).replace(',', ''))
                numeric_count += 1
            except ValueError:
                pass
        
        return numeric_count / len(values) > 0.8
    
    def get_enhanced_filter_options(self, table_columns):
        """
        Get enhanced filter options with property analysis.
        This provides better categorization and filtering options.
        
        input:
            - table_columns: list of column configurations
        output:
            - dictionary with enhanced filter information
        """
        filter_options = {}
        
        for column in table_columns:
            property_name = column['property']
            analysis = self.analyze_property_characteristics(property_name)
            
            filter_options[property_name] = {
                'values': analysis['unique_values'],
                'characteristics': analysis,
                'filter_type': analysis['filter_type']
            }
        
        return filter_options
    
    def get_sortable_value(self, instance_data, sort_property):
        """
        Get a sortable value for the given property from instance data.
        Handles different data types appropriately for sorting.
        Returns a tuple (sort_priority, sort_value) to ensure type-safe sorting.
        
        input:
            - instance_data: the instance data dictionary
            - sort_property: the property to extract for sorting
        output:
            - a tuple (sort_priority, sort_value) where:
              - sort_priority: 0 for valid data, 1 for empty data (to sort empty last)
              - sort_value: the actual sortable value (always same type within priority)
        """
        # Get the raw property value
        property_value = instance_data.get('properties', {}).get(sort_property, '')
        
        # Handle empty values - sort them last with priority 1
        if not property_value or property_value == '':
            return (1, 'empty')  # Priority 1 means sort last, 'empty' is the sort value
        
        # Convert to string for consistent handling
        str_value = str(property_value).strip()
        
        # Priority 0 means sort first (actual data)
        sort_priority = 0
        
        # Try to convert to number if it looks numeric
        try:
            # Check if it's a pure number
            if str_value.replace('.', '').replace('-', '').replace('+', '').isdigit():
                # Return as string representation of number for consistent sorting
                # Pad with zeros to ensure proper numerical sorting
                try:
                    num_value = float(str_value)
                    # Format as padded string to maintain sort order
                    return (sort_priority, f"{num_value:020.6f}")
                except ValueError:
                    pass
        except (ValueError, AttributeError):
            pass
        
        # Try to parse as date if it looks like a date
        try:
            import re
            # Check for common date patterns
            date_patterns = [
                r'\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
                r'\d{2}/\d{2}/\d{4}',  # MM/DD/YYYY
                r'\d{4}/\d{2}/\d{2}',  # YYYY/MM/DD
                r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}',  # ISO datetime
            ]
            
            for pattern in date_patterns:
                if re.search(pattern, str_value):
                    try:
                        from datetime import datetime
                        # Try different date parsing approaches
                        for date_format in ['%Y-%m-%d', '%m/%d/%Y', '%Y/%m/%d', '%Y-%m-%dT%H:%M:%S']:
                            try:
                                # Handle date format extraction properly
                                date_str = str_value
                                if 'T' in date_format and 'T' in str_value:
                                    # Keep the full datetime string
                                    pass
                                elif 'T' not in date_format and 'T' in str_value:
                                    # Extract just the date part
                                    date_str = str_value.split('T')[0]
                                
                                parsed_date = datetime.strptime(date_str, date_format)
                                # Return as ISO format string for consistent sorting
                                return (sort_priority, parsed_date.strftime('%Y-%m-%d %H:%M:%S'))
                            except ValueError:
                                continue
                    except ImportError:
                        pass
        except Exception:
            pass
        
        # Default to case-insensitive string sorting
        return (sort_priority, str_value.lower())
    
    def get_instances(self, search_query=None):
        """
        List all instances in the persistance folder.
        If search_query is provided, filter instances by title and content.

        input:
            - search_query: optional search string to filter instances
        output:
            - a dictionary of instances (filtered if search_query provided)
        """
        if search_query is None or search_query.strip() == "":
            return self.__cached_items.copy()
        
        # Convert search query to lowercase for case-insensitive search
        search_lower = search_query.lower().strip()
        filtered_items = {}
        
        for item_id, item_data in self.__cached_items.items():
            # Search in title
            title_match = search_lower in item_data.get("title", "").lower()
            
            # Search in searchable content
            content_match = search_lower in item_data.get("searchable_content", "")
            
            if title_match or content_match:
                filtered_items[item_id] = item_data
        
        return filtered_items
    
    def delete_instance(self, id: str):
        """
        Delete an instance from the persistance folder.
        input:
            - id: the identifier of the instance to delete
            
            output:
                - None
        """
        if id in self.__cached_items:
            os.remove(self.__cached_items[id]["filename"])
            del self.__cached_items[id]
        else:
            raise Exception(f"Could not find instance with id {id}")
    
    def save_instance(self, data: dict):
        """
        Save an instance to the persistance folder.
        input:
            - data: the data to save
            
            output:
                - None
        """
        if "@id" not in data:
            session_id = uuid.uuid4()
            id = f"{self.__base_url}/{session_id}"
            data["@id"] = id
        else:
            session_id = data["@id"].split("/")[-1]

        filename = os.path.join(self.__folder_location, f"{session_id}.jsonld")
        with open(filename, 'w') as f:
            json.dump(data, f, indent=4)
        self.__parse_jsonld_file(filename)
    
    # ============================================
    # Project Management Methods
    # ============================================
    
    def create_project(self, project_name: str = None, project_metadata: dict = None):
        """
        Create a new project folder with metadata.
        
        input:
            - project_name: name of the project (optional, for simple form creation)
            - project_metadata: optional metadata for the project (JSON-LD)
        output:
            - project_id: unique identifier for the project
        """
        project_id = str(uuid.uuid4())
        project_folder = os.path.join(self.__folder_location, f"project_{project_id}")
        os.makedirs(project_folder, exist_ok=True)
        
        # Create project metadata file
        if project_metadata is None:
            project_metadata = {}
        
        project_metadata["@id"] = f"{self.__base_url}/project/{project_id}"
        project_metadata["@type"] = "Project"
        
        # Only add project_name field if explicitly provided (for simple form creation)
        # For template-based creation, the name is within the CEDAR template data
        if project_name is not None:
            project_metadata["project_name"] = project_name
        
        project_metadata["pav:createdOn"] = datetime.datetime.now().isoformat()
        
        metadata_file = os.path.join(project_folder, "project_metadata.jsonld")
        with open(metadata_file, 'w') as f:
            json.dump(project_metadata, f, indent=4)
        
        return project_id
    
    def _extract_project_name_from_metadata(self, metadata: dict, name_predicate: str = None) -> str:
        """
        Extract project name from metadata using configured predicate or fallback.
        
        input:
            - metadata: project metadata dictionary
            - name_predicate: optional predicate/field path from config (e.g., 'project_name' or 'General.Name')
        output:
            - project name string
        """
        # If a name_predicate is configured, use it
        if name_predicate:
            # Try nested property extraction (supports dot notation)
            value = self.__extract_nested_property_value(metadata, name_predicate)
            if value:
                return value
        
        # Fallback: First check if there's a hard-coded project_name (for simple form projects)
        if "project_name" in metadata and not isinstance(metadata["project_name"], dict):
            return metadata["project_name"]
        
        # Try to extract from common CEDAR template fields
        for field_name in ["project_name", "name", "title"]:
            if field_name in metadata:
                field_value = metadata[field_name]
                if isinstance(field_value, dict) and "@value" in field_value:
                    return field_value["@value"]
                elif isinstance(field_value, str):
                    return field_value
        
        return "Unnamed Project"
    
    def _extract_cedar_field_value(self, metadata: dict, field_predicate: str) -> str:
        """
        Extract a field value from CEDAR template metadata using configured predicate.
        
        input:
            - metadata: project metadata dictionary
            - field_predicate: predicate/field path from config (e.g., 'description' or 'General.Description')
        output:
            - field value as string, or empty string if not found
        """
        if not field_predicate:
            return ""
        
        # Try nested property extraction (supports dot notation)
        value = self.__extract_nested_property_value(metadata, field_predicate)
        if value:
            return value
        
        # Fallback: direct field lookup
        if field_predicate in metadata:
            field_value = metadata[field_predicate]
            if isinstance(field_value, dict) and "@value" in field_value:
                return field_value["@value"]
            elif isinstance(field_value, str):
                return field_value
        
        return ""
    
    def get_all_projects(self, config: dict = None):
        """
        Get all projects from the storage folder.
        
        input:
            - config: optional configuration dictionary for field extraction
        output:
            - dictionary of projects with their metadata
        """
        projects = {}
        
        if not os.path.exists(self.__folder_location):
            return projects
        
        # Extract predicates from config if provided
        name_predicate = None
        description_predicate = None
        if config and "projects" in config and "project_metadata_template" in config["projects"]:
            template_config = config["projects"]["project_metadata_template"]
            name_predicate = template_config.get("name_predicate") or template_config.get("title_predicate")
            description_predicate = template_config.get("description_predicate")
        
        for item in os.listdir(self.__folder_location):
            item_path = os.path.join(self.__folder_location, item)
            if os.path.isdir(item_path) and item.startswith("project_"):
                project_id = item.replace("project_", "")
                metadata_file = os.path.join(item_path, "project_metadata.jsonld")
                
                if os.path.exists(metadata_file):
                    try:
                        with open(metadata_file, 'r') as f:
                            metadata = json.load(f)
                            project_name = self._extract_project_name_from_metadata(metadata, name_predicate)
                            created_on = metadata.get("pav:createdOn", "")
                            
                            # Extract description using configured predicate
                            description = ""
                            if description_predicate:
                                description = self._extract_cedar_field_value(metadata, description_predicate)
                            
                            projects[project_id] = {
                                "id": project_id,
                                "name": project_name,
                                "description": description,
                                "created_on": created_on,
                                "metadata": metadata,
                                "folder": item_path
                            }
                    except Exception as e:
                        print(f"Error loading project {project_id}: {e}")
        
        return projects
    
    def get_project(self, project_id: str, config: dict = None):
        """
        Get a specific project by ID.
        
        input:
            - project_id: the project identifier
            - config: optional configuration dictionary for field extraction
        output:
            - project data dictionary
        """
        projects = self.get_all_projects(config)
        if project_id in projects:
            return projects[project_id]
        else:
            raise Exception(f"Project {project_id} not found")
    
    def project_exists(self, project_id: str) -> bool:
        """
        Check if a project exists.
        
        input:
            - project_id: the project identifier
        output:
            - True if exists, False otherwise
        """
        project_folder = os.path.join(self.__folder_location, f"project_{project_id}")
        return os.path.exists(project_folder)
    
    def save_project_phase_response(self, project_id: str, phase_name: str, response_data: dict):
        """
        Save a questionnaire response for a specific project phase.
        
        input:
            - project_id: the project identifier
            - phase_name: the name of the phase
            - response_data: the JSON-LD response data
        output:
            - response_id: unique identifier for the response
        """
        if not self.project_exists(project_id):
            raise Exception(f"Project {project_id} not found")
        
        project_folder = os.path.join(self.__folder_location, f"project_{project_id}")
        
        # Generate or extract response ID
        if "@id" in response_data:
            response_id = response_data["@id"].split("/")[-1]
        else:
            response_id = str(uuid.uuid4())
            response_data["@id"] = f"{self.__base_url}/project/{project_id}/phase/{response_id}"
        
        # Add phase metadata
        response_data["project_phase"] = phase_name
        response_data["project_id"] = f"{self.__base_url}/project/{project_id}"
        
        if "pav:createdOn" not in response_data:
            response_data["pav:createdOn"] = datetime.datetime.now().isoformat()
        else:
            response_data["pav:lastUpdatedOn"] = datetime.datetime.now().isoformat()
        
        # Save to file
        # Sanitize phase name for filename
        safe_phase_name = phase_name.replace(" ", "_").replace(":", "").replace("/", "_")
        filename = os.path.join(project_folder, f"phase_{safe_phase_name}_{response_id}.jsonld")
        
        with open(filename, 'w') as f:
            json.dump(response_data, f, indent=4)
        
        return response_id
    
    def get_project_phase_responses(self, project_id: str):
        """
        Get all questionnaire responses for a project, organized by phase.
        
        input:
            - project_id: the project identifier
        output:
            - dictionary of responses organized by phase name
        """
        if not self.project_exists(project_id):
            raise Exception(f"Project {project_id} not found")
        
        project_folder = os.path.join(self.__folder_location, f"project_{project_id}")
        responses_by_phase = {}
        
        for filename in os.listdir(project_folder):
            if filename.startswith("phase_") and filename.endswith(".jsonld"):
                filepath = os.path.join(project_folder, filename)
                try:
                    with open(filepath, 'r') as f:
                        response_data = json.load(f)
                        phase_name = response_data.get("project_phase", "Unknown Phase")
                        response_id = response_data.get("@id", "").split("/")[-1]
                        
                        if phase_name not in responses_by_phase:
                            responses_by_phase[phase_name] = []
                        
                        responses_by_phase[phase_name].append({
                            "id": response_id,
                            "filename": filepath,
                            "data": response_data,
                            "created_on": response_data.get("pav:createdOn", ""),
                            "updated_on": response_data.get("pav:lastUpdatedOn", "")
                        })
                except Exception as e:
                    print(f"Error loading response from {filename}: {e}")
        
        return responses_by_phase
    
    def get_project_phase_response(self, project_id: str, response_id: str):
        """
        Get a single questionnaire response for a project phase.
        
        input:
            - project_id: the project identifier
            - response_id: the response identifier
        output:
            - dictionary with response data and metadata
        """
        if not self.project_exists(project_id):
            raise Exception(f"Project {project_id} not found")
        
        project_folder = os.path.join(self.__folder_location, f"project_{project_id}")
        
        # Search for the response file
        for filename in os.listdir(project_folder):
            if filename.startswith("phase_") and filename.endswith(f"{response_id}.jsonld"):
                filepath = os.path.join(project_folder, filename)
                with open(filepath, 'r') as f:
                    response_data = json.load(f)
                    return {
                        "id": response_id,
                        "filename": filepath,
                        "data": response_data,
                        "phase_name": response_data.get("project_phase", "Unknown Phase"),
                        "created_on": response_data.get("pav:createdOn", ""),
                        "updated_on": response_data.get("pav:lastUpdatedOn", "")
                    }
        
        raise Exception(f"Response {response_id} not found in project {project_id}")
    
    def delete_project(self, project_id: str):
        """
        Delete a project and all its associated data.
        
        input:
            - project_id: the project identifier
        """
        if not self.project_exists(project_id):
            raise Exception(f"Project {project_id} not found")
        
        import shutil
        project_folder = os.path.join(self.__folder_location, f"project_{project_id}")
        shutil.rmtree(project_folder)
    
    def update_project_metadata(self, project_id: str, updated_metadata: dict):
        """
        Update project metadata.
        
        input:
            - project_id: the project identifier
            - updated_metadata: updated project metadata
        """
        if not self.project_exists(project_id):
            raise Exception(f"Project {project_id} not found")
        
        project_folder = os.path.join(self.__folder_location, f"project_{project_id}")
        metadata_file = os.path.join(project_folder, "project_metadata.jsonld")
        
        # Preserve critical fields
        if os.path.exists(metadata_file):
            with open(metadata_file, 'r') as f:
                existing = json.load(f)
                updated_metadata["@id"] = existing.get("@id")
                updated_metadata["pav:createdOn"] = existing.get("pav:createdOn")
        
        updated_metadata["pav:lastUpdatedOn"] = datetime.datetime.now().isoformat()
        
        with open(metadata_file, 'w') as f:
            json.dump(updated_metadata, f, indent=4)