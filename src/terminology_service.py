from rdflib import Graph, Namespace, URIRef, Literal
from rdflib.namespace import RDF, RDFS, OWL

class TerminologyService:
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
                results.append({"class": s, "label": o.value})
        return results
    
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
                    results.append({"class": s, "label": o.value})
        return results