import os

from kubernetes import client, config

config.load_incluster_config()

v1_client = client.CoreV1Api()


image_name = os.environ["IMAGE"]
node_tag_prefix = "spack.io/image-pulled"
node_tag = os.path.join(node_tag_prefix, image_name)
body = {"metadata": {"labels": {node_tag: "true"}}}


# TODO: Use k8s API to tag2 node with imagepulled label
# TODO: Fetch node
res = v1_client.patch_node(node.metadata.name, body)
