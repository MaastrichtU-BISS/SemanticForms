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
            
            self.__cached_items[id] = {
                "title": title_found,
                "filename": filename,
                "time": metadata['pav:createdOn'],
                "searchable_content": searchable_content
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