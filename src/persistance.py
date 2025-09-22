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
        predicate = uri_tree.pop(0)
        for key in metadata["@context"]:
            value = metadata["@context"][key]
            if value == predicate:
                titleTag = key
                if len(uri_tree) > 0:
                    return self.__find_title_recursively(metadata[titleTag], uri_tree)
                else:
                    return metadata[titleTag]["@value"]
        return "No title found"
                    

    
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
            
            self.__cached_items[id] = {
                "title": title_found,
                "filename": filename,
                "time": metadata['pav:createdOn']
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

    def get_instances(self):
        """
        List all instances in the persistance folder.

        output:
            - a dictionary of instances
        """
        return self.__cached_items.copy()
    
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