from rdflib import Graph, Namespace, URIRef, Literal
from rdflib.namespace import RDF, RDFS, OWL

class TerminologyService:
    """
    A base class for terminology services that provides an interface for searching classes in an ontology.
    This class defines the methods that should be implemented by any concrete terminology service.
    """
    def search_class_on_label(self, text):
        """
        Search for classes in the ontology by their label. The search of this label is case insensitive, and partial (there might be a prefix or suffix of the search term).
        :param text: The text to search for.
        :return: A list of class URIs that match the label.
        """
        raise NotImplementedError("This method should be implemented by subclasses.")

    def search_class_on_label_and_subclass(self, uri, text):
        """
        Search for classes in the ontology by their label and subclass (recursive). The search of this label is case insensitive, and partial (there might be a prefix or suffix of the search term).
        :param uri: The URI of the class to search for subclasses (recursive).
        :param text: The text to search for.
        :return: A list of class URIs that match the label and are subclasses of the given URI.
        """
        raise NotImplementedError("This method should be implemented by subclasses.")
    
    def __order_by_string_similarity(self, results, text):
        """
        Order the results by string similarity to the given text.
        :param results: The list of results to order.
        :param text: The text to compare against.
        :return: The ordered list of results.
        """
        from difflib import SequenceMatcher
        return sorted(results, key=lambda x: SequenceMatcher(None, x["label"], text).ratio(), reverse=True)

class SPARQLTerminologyService(TerminologyService):
    """
    A service for searching classes in an ontology based on their labels using SPARQL queries.
    This service connects to a SPARQL endpoint and provides methods to search for classes by their labels.
    It supports searching for classes by label, and also allows searching for subclasses recursively.
    """
    def __init__(self, sparql_endpoint: str):
        # test if the SPARQL endpoint is reachable
        from SPARQLWrapper import SPARQLWrapper, JSON
        sparql = SPARQLWrapper(sparql_endpoint)
        sparql.setQuery("SELECT * WHERE { ?s ?p ?o } LIMIT 1")
        sparql.setReturnFormat(JSON)
        try:
            sparql.query().convert()
        except Exception as e:
            raise ValueError(f"Could not connect to SPARQL endpoint: {sparql_endpoint}. Error: {e}")
        
        # if the endpoint is reachable, set it
        self.sparql_endpoint = sparql_endpoint

    def search_class_on_label(self, text):
        """
        Search for classes in the ontology by their label. The search of this label is case insensitive, and partial (there might be a prefix or suffix of the search term).
        :param text: The text to search for.
        :return: A list of class URIs that match the label.
        """

        text_regex = text.split(" ")
        regex_string = ""
        for item in text_regex:
            regex_string += f"(?=.*\\\\b{item}\\\\b)"

        print(f"Searching for classes with label containing: {text} (regex: {regex_string})")
        query = f"""
        SELECT DISTINCT ?class (str(?label_literal) AS ?label) ?graph WHERE {{
            GRAPH ?graph {{
                ?class a owl:Class .
                ?class rdfs:label ?label_literal .
                FILTER (regex(str(?label_literal), "{regex_string}", "i"))
            }}
        }}
        """

        print(f"SPARQL Query: {query}")

        results = self.execute_sparql_query(query)
        return_value = [{"class": str(result["class"]["value"]), "label": result["label"]["value"], "graph": result["graph"]["value"]} for result in results]
        return super()._TerminologyService__order_by_string_similarity(return_value, text)
    
    def execute_sparql_query(self, query):
        """
        Execute a SPARQL query against the SPARQL endpoint.
        :param query: The SPARQL query to execute.
        :return: The results of the query.
        """
        from SPARQLWrapper import SPARQLWrapper, JSON
        sparql = SPARQLWrapper(self.sparql_endpoint)
        sparql.setQuery(query)
        sparql.setReturnFormat(JSON)
        results = sparql.query().convert()
        return results["results"]["bindings"]

    def search_class_on_label_and_subclass(self, uri, text):
        """
        Search for classes in the ontology by their label and subclass (recursive). The search of this label is case insensitive, and partial (there might be a prefix or suffix of the search term).
        :param uri: The URI of the class to search for subclasses (recursive).
        :param text: The text to search for.
        :return: A list of class URIs that match the label and are subclasses of the given URI.
        """
        text_regex = text.split(" ")
        regex_string = ""
        for item in text_regex:
            regex_string += f"(?=.*\\\\b{item}\\\\b)"

        print(f"Searching for classes with label containing: {text} (regex: {regex_string}) and subclass of: {uri}")

        query = f"""
        SELECT DISTINCT ?class (str(?label_literal) AS ?label) ?graph WHERE {{
            GRAPH ?graph {{
                ?class a owl:Class .
                ?class rdfs:subClassOf* <{uri}> .
                ?class rdfs:label ?label_literal .
                FILTER (regex(str(?label_literal), "{regex_string}", "i"))
            }}
        }}
        """

        print(f"SPARQL Query: {query}")

        results = self.execute_sparql_query(query)
        return_value = [{"class": str(result["class"]["value"]), "label": result["label"]["value"], "graph": result["graph"]["value"]} for result in results]
        return super()._TerminologyService__order_by_string_similarity(return_value, text)

class MemoryTerminologyService(TerminologyService):
    """
    A service for searching classes in an ontology based on their labels.
    This service uses an in-memory RDF graph to store the ontology and provides methods to search for classes by their labels.
    It supports searching for classes by label, and also allows searching for subclasses recursively.
    """
    def __init__(self, ontology_path: list):
        self.graph = Graph()
        for path in ontology_path:
            self.graph.parse(path)

    def search_class_on_label(self, text):
        """
        Search for classes in the ontology by their label. The search of this label is case insensitive, and partial (there might be a prefix or suffix of the search term).
        :param label: The text to search for.
        :return: A list of class URIs that match the label.
        """
        results = []
        text = text.lower()
        for s, p, o in self.graph.triples((None, RDFS.label, None)):
            if isinstance(o, Literal) and text in o.value.lower():
                results.append({"class": str(s), "label": o.value})
        
        return results #self.__make_results_unique(results)
    
    def __make_results_unique(self, results):
        """
        Make the results unique based on class URI.
        :param results: The list of results to make unique.
        :return: A list of unique results.
        """
        unique_results = []
        seen = set()
        for result in results:
            if result["class"] not in seen:
                unique_results.append(result)
                seen.add(result["class"])
        return unique_results
    
    def search_class_on_label_and_subclass(self, uri, text):
        """
        Search for classes in the ontology by their label and subclass (recursive). The search of this label is case insensitive, and partial (there might be a prefix or suffix of the search term).
        :param uri: The URI of the class to search for subclasses (recursive).
        :param text: The text to search for.
        :return: A list of class URIs that match the label and are subclasses of the given URI.
        """
        results = []
        text = text.lower()
        for s, p, o in self.graph.triples((None, RDFS.label, None)):
            if isinstance(o, Literal) and text in o.value.lower():
                # Check if the class is a subclass of the given URI
                if self.is_subclass(s, uri):
                    results.append({"class": str(s), "label": o.value})
        return results #self.__make_results_unique(results)