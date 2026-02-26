import json
from pyvis.network import Network
import rdflib
import networkx as nx
import matplotlib.pyplot as plt

def visualize_graph(filename):

    # Parse JSON-LD into RDF graph
    g = rdflib.Graph()
    g.parse(filename, format="json-ld")

    # Convert RDF to NetworkX graph
    G = nx.DiGraph()

    for subj, pred, obj in g:
        G.add_edge(str(subj), str(obj), label=str(pred))

    # Draw graph
    pos = nx.spring_layout(G, k=0.5)
    nx.draw(G, pos, with_labels=True, node_size=100, font_size=8)

    # Draw edge labels (predicates)
    # edge_labels = {(u, v): d["label"] for u, v, d in G.edges(data=True)}
    # nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_size=6)

    plt.title("JSON-LD Knowledge Graph Visualization")
    plt.show()

# show high-level values
def visualize_MainEntity(filename):

    with open(filename) as f:
        data = json.load(f)
    net = Network(height="750px", width="100%")
    main_entity = data.get("@type", "MainEntity")
    net.add_node(main_entity, size=30)
    for key, value in data.items():
        if key.startswith("@"):
            continue
        group_node = key
        net.add_node(group_node, label=key, group=main_entity)
        net.add_edge(main_entity, group_node)

    for i, field in enumerate(net.node_ids):
        if i==0:
            print(f"{field}")
        elif i == len(net.node_ids) - 1:
            print(f"└── {field}")
        else:
            print(f"├── {field}")

# show structure for General model information

# show structure for input features
def visualize_inputdata(filename):
    with open(filename) as f:
        data = json.load(f)

    items = data.get("Input data1", [])

    print("Input data1")
    for i, item in enumerate(items):
        label = item.get("Input label", {}).get("@value", f"Feature_{i + 1}")

        if i == len(items) - 1:
            prefix = "└──"
        else:
            prefix = "├──"

        print(f"{prefix} {label}")

        fields = [k for k in item.keys() if not k.startswith("@")]

        for j, field in enumerate(fields):
            if j == len(fields) - 1:
                sub_prefix = "    └──"
            else:
                sub_prefix = "    ├──"
            print(f"{sub_prefix} {field} {item.get(field)}")

            if j <3:
                continue
            else:
                break


# show structure for performance metrics