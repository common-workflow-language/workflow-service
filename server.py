import connexion
from connexion.resolver import Resolver
import connexion.utils as utils
import myapp

app = connexion.App(__name__, specification_dir='swagger/')
def rs(x):
    return utils.get_function_from_name("cwl_runner_wes." + x)

app.add_api('proto/workflow_execution.swagger.json', resolver=Resolver(rs))

app.run(port=8080)
