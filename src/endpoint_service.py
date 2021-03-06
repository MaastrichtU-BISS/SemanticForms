from SPARQLWrapper import SPARQLWrapper, POST, DIGEST, JSON
import logging

class SPARQLEndpoint:
    def __init__(self, sparql_url, sparqlUpdateUrl=None):
        """
        The SPARQLEndpoint class manages communication to the SPARQL endpoint.
        sparql_url: the SPARQL endpoint URL
        sparqlUpdateUrl: optional, if the endpoint uses a separate update url, provide this URL here
        """
        self.__sparql_url = sparql_url
        self.__sparql_update_url = sparql_url
        if sparqlUpdateUrl is not None:
            self.__sparql_update_url = sparqlUpdateUrl
    
    def list_instances(self):
        """
        Retrieve all instances stored in the SPARQL endpoint
        """
        
        query = """
        prefix pav: <http://purl.org/pav/>

        select distinct ?instance ?time
        where { 
            ?instance pav:createdOn ?time.
        }
        """

        sparql = SPARQLWrapper(self.__sparql_url)
        sparql.setQuery(query)
        sparql.setReturnFormat(JSON)
        results = sparql.query().convert()
        return results["results"]["bindings"]
    
    def describe_instance(self, instance_uri):
        """
        Retrieve the direct properties of the given instance
        """
        sparql = SPARQLWrapper(self.__sparql_url)
        sparql.setQuery("""
        SELECT ?predicate ?object
        WHERE {
            <%s> ?predicate ?object.
        }
        """ % instance_uri)
        sparql.setReturnFormat(JSON)
        results = sparql.query().convert()
        return results["results"]["bindings"]
    
    def get_instance_links(self, instance_uri):
        """
        Retrieve the references of this instance
        """
        sparql = SPARQLWrapper(self.__sparql_url)
        sparql.setQuery("""
        SELECT ?predicate ?object
        WHERE {
            ?subject ?predicate <%s>.
        }
        """ % instance_uri)
        sparql.setReturnFormat(JSON)
        results = sparql.query().convert()
        return results["results"]["bindings"]

    def drop_instance(self, identifier):
        """
        Delete the form instance
        """
        query = "DROP GRAPH <%s>" % identifier
        sparql = SPARQLWrapper(self.__sparql_update_url)
        sparql.setMethod(POST)
        sparql.setQuery(query)

        logging.debug(query)

        results = sparql.query()
        logging.debug(results.response.read())

    def store_instance(self, rdf_string, graph_uri=None):
        """
        Store data to a SPARQL endpoint.
        rdf_string: containing the triples (format=nt) to store
        graph_uri: optional, to set the named graph
        """
        queryData = "INSERT DATA { %s }" % rdf_string
        if graph_uri is not None:
            queryData = "INSERT DATA { GRAPH <%s> { %s } }" % (graph_uri, rdf_string)

        sparql = SPARQLWrapper(self.__sparql_update_url)
        sparql.setMethod(POST)
        sparql.setQuery(queryData)

        logging.debug(f"Storing data to endpoint {self.__sparql_update_url}")
        logging.debug(queryData)

        results = sparql.query()
        logging.debug(results.response.read())