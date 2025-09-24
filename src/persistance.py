import os, json, uuid

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
        """
        # First, try the original recursive search approach
        try:
            predicate = uri_tree[0]  # Don't modify the original list
            for key in metadata.get("@context", {}):
                value = metadata["@context"][key]
                if value == predicate:
                    titleTag = key
                    if len(uri_tree) > 1:
                        return self.__find_title_recursively(metadata[titleTag], uri_tree[1:])
                    else:
                        if titleTag in metadata and isinstance(metadata[titleTag], dict) and "@value" in metadata[titleTag]:
                            return metadata[titleTag]["@value"]
                        elif titleTag in metadata:
                            return str(metadata[titleTag])
        except (KeyError, IndexError, TypeError):
            pass
        
        # Enhanced search: Look for common title patterns in CEDAR JSON-LD
        title_patterns = [
            # Direct patterns
            ["title"],
            ["name"], 
            ["label"],
            ["rdfs:label"],
            ["schema:name"],
            ["dct:title"],
            # CEDAR nested patterns - look for "General Model Information" -> "Title"
            ["General Model Information", "Title"],
            # Other nested patterns
            ["metadata", "title"],
            ["metadata", "name"],
        ]
        
        for pattern in title_patterns:
            title = self.__find_title_by_path(metadata, pattern)
            if title and title != "No title found":
                return title
                    
        return "No title found"
    
    def __find_title_by_path(self, data, path):
        """
        Navigate through nested structure following the given path to find a title.
        """
        current = data
        for step in path:
            if isinstance(current, dict) and step in current:
                current = current[step]
            else:
                return None
        
        # Extract value if it's in @value format
        if isinstance(current, dict) and "@value" in current:
            return current["@value"] if current["@value"] is not None else None
        elif isinstance(current, str):
            return current
        
        return None

    def __extract_searchable_content(self, metadata):
        """
        Extract all searchable text content from JSON-LD metadata.
        This includes values from fields that contain @value properties.
        """
        searchable_text = []
        
        def extract_values(obj):
            if isinstance(obj, dict):
                if "@value" in obj:
                    # Extract the actual value from @value fields
                    searchable_text.append(str(obj["@value"]))
                else:
                    # Recursively process nested objects
                    for key, value in obj.items():
                        # Skip metadata fields like @id, @context, pav:createdOn, etc.
                        if not key.startswith("@") and not key.startswith("pav:") and not key.startswith("schema:isBasedOn"):
                            extract_values(value)
            elif isinstance(obj, list):
                for item in obj:
                    extract_values(item)
        
        extract_values(metadata)
        return " ".join(searchable_text).lower()  # Convert to lowercase for case-insensitive search
                    

    
    def __parse_jsonld_file(self, filename: str):
        """
        Read JSON-LD object from filename, and parse the title and identifier of the object.
        input:
            - filename: the path of the file to parse
        """
        with open(filename, 'r') as f:
            metadata = json.load(f)
            id = metadata["@id"].replace(self.__base_url + "/", "")
            title_found = self.__find_title_recursively(metadata, self.__title_uri.split("|"))
            
            # Extract searchable content from all fields
            searchable_content = self.__extract_searchable_content(metadata)
            
            # Store complete metadata for property extraction
            self.__cached_items[id] = {
                "title": title_found,
                "filename": filename,
                "time": metadata['pav:createdOn'],
                "searchable_content": searchable_content,
                "metadata": metadata
            }
    
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
            
            # Extract each configured property
            for column in table_columns:
                property_name = column['property']
                property_value = self.__extract_property_value(instance_data['metadata'], property_name)
                enhanced_data['properties'][property_name] = property_value
            
            enhanced_instances[instance_id] = enhanced_data
        
        return enhanced_instances

    def __extract_property_value(self, metadata, property_name):
        """
        Extract a specific property value from JSON-LD metadata.
        Now supports nested properties using dot notation (e.g., "metadata.project", "details.team.lead").
        
        input:
            - metadata: the JSON-LD metadata object
            - property_name: the property to extract (supports dot notation for nested properties)
        output:
            - the property value as a string, or empty string if not found
        """
        # Handle nested property paths (e.g., "metadata.project", "details.team.lead")
        if '.' in property_name:
            return self.__extract_nested_property_value(metadata, property_name)
        
        # First try direct property access
        if property_name in metadata:
            value = metadata[property_name]
            if isinstance(value, dict) and "@value" in value:
                return value["@value"]
            elif isinstance(value, str):
                return value
        
        # Try to find through context mapping
        context = metadata.get("@context", {})
        for key, uri in context.items():
            if key == property_name and key in metadata:
                value = metadata[key]
                if isinstance(value, dict) and "@value" in value:
                    return value["@value"]
                elif isinstance(value, str):
                    return value
        
        # Special cases for common properties
        if property_name == "title":
            return self.__find_title_recursively(metadata, self.__title_uri.split("|"))
        elif property_name == "creation_date" or property_name == "date_created":
            return metadata.get("pav:createdOn", "")
        elif property_name == "updated_date" or property_name == "date_updated":
            return metadata.get("pav:lastUpdatedOn", "")
        
        return ""
    
    def __extract_nested_property_value(self, metadata, property_path):
        """
        Extract a nested property value using dot notation path.
        Similar to __find_title_by_path but for any property.
        Enhanced to handle arrays and complex JSON-LD structures.
        
        input:
            - metadata: the JSON-LD metadata object
            - property_path: dot-separated path (e.g., "metadata.project", "details.team.lead")
        output:
            - the property value as a string, or empty string if not found
        """
        path_parts = property_path.split('.')
        current = metadata
        
        # Navigate through the nested structure
        for part in path_parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return ""
        
        # Extract value based on the final structure
        return self.__extract_value_from_structure(current)
    
    def __extract_value_from_structure(self, current):
        """
        Extract a meaningful value from various JSON-LD structures.
        Handles arrays, @value objects, direct values, and complex nested structures.
        
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
        elif isinstance(current, str):
            return current
        elif isinstance(current, (int, float)):
            return str(current)
        elif isinstance(current, dict):
            # If it's a dict without @value, try to find a meaningful string representation
            # Look for common value fields in order of preference
            for value_key in ["@value", "value", "name", "title", "label", "rdfs:label"]:
                if value_key in current:
                    val = current[value_key]
                    if isinstance(val, dict) and "@value" in val:
                        return val["@value"] if val["@value"] is not None else ""
                    elif isinstance(val, (str, int, float)):
                        return str(val)
            
            # If no standard value field found, try to get a string representation
            # This handles cases where the dict might have other meaningful content
            if len(current) == 1:
                # If there's only one key, use its value
                key, val = next(iter(current.items()))
                if isinstance(val, (str, int, float)):
                    return str(val)
            
            return ""
        
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
            value = self.__extract_property_value(instance_data['metadata'], property_name)
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
            value = self.__extract_property_value(instance_data['metadata'], property_name)
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
            session_id = data["@id"].replace(self.__base_url + "/", "")

        filename = os.path.join(self.__folder_location, f"{session_id}.jsonld")
        with open(filename, 'w') as f:
            json.dump(data, f, indent=4)
        self.__parse_jsonld_file(filename)