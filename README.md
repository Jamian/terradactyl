<br/>
<img src="terradactyl/cartographer/static/img/terradactyl-logo.svg" width=175em></img>
<br/>
<br/>

[![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=Jamian_terradactyl&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=Jamian_terradactyl) [![Coverage](https://sonarcloud.io/api/project_badges/measure?project=Jamian_terradactyl&metric=coverage)](https://sonarcloud.io/summary/new_code?id=Jamian_terradactyl)

<h1>Terradactyl</h1>

Terradactyl provides a bird's eye view of your Terraform states by analysing your remote state files and parsing them into a Tinkerpop graph database. With this you can explore your state network, viewing individuals or identifiying dependencies. If you want to run a state, Terradactyl will even provide a path of dependencies to run first, based on their own, in order to get to where you want to be.

Initially this project was just a bit of fun to help identify the run order for states. It quickly became apparent though, that you can build out some really interesting visualizations and generate useful information about your Terraform real estate using the Terraform Cloud APIs and some state parsing.

:warning: Terradactyl currently only supports *Terraform Cloud* as we rely heavily on their APIs to retrieve state revision history.

## Current Features
* Identifying state run orders (the order in which you must run all states, start to finish to get to the one you want. E.g. in a DR scenario or setting up a redundant environment).
* Visualizing State interactions/dependencies at the Terraform Cloud Organizational level. At a glance identify larger states, _Terraform version drift_.
* Exploration of individual states: viewing the local dependency networks, resource counts, growth over time.
* Identify redundant dependencies between states. This works by parsing state files (no actual resource data is stored other than some metadata like names, counts) and checking which data.terraform_remote_state namespaces are not used. *This relies solely on the use of `terraform_remote_state` blocks. If you don't use these (against best practice) this functionality won't be accurate.

## Screenshots
Below show the two main screens - viewing your overall and individual state networks.

![Explore States](docs/images/screenshot-explore-states.png)
![View State](docs/images/screenshot-view-state.png)

## Local Development
### Putting it together
#### Install Requirements
1. Set up a Virtual Environemnt: `virtualenv -p python3 venv`
2. Install python dependencies: `pip install -r requirements.txt`
3. Install Docker - https://docs.docker.com/get-docker/
#### Running the Dev Environment
Environment Variables
```
export TERRADACTYL_DJANGO_DEBUG=True
export DJANGO_SECRET_KEY=supersecret
export TERRADACTYL_ENCRYPTED_CHAR_FIELD_KEY=oooimakey
export TERRADACTYL_ENCRYPTED_CHAR_FIELD_SALT=oooimasalt
```
1. Start redis - `brew services start redis`
2. Confirm redis working (will reply PONG): `redis-cli ping`
3. Start the TinkerPOP Gremlin server - `docker run -p 8182:8182 -d --name terradactyl-gremlin tinkerpop/gremlin-server:3.6`
3. Start the Django sync web worker: `cd terradactyl && python manage.py runserver`
4. Start the async worker: `cd terradactyl && celery -A terradactyl worker -l INFO`

## Known Issues

### Conditional Data Lookups
If a `data.terraform_remote_state` resource is created based on some condition, then the Terraform Remote State will not include the resource object when the condition evaluates to `false`. It will still however falsely identify it as a dependency on the resource that references it. In the following example, when `var.bob_required` is `false` then the data lookup `bob_ross` is not created. It is still however a dependency in the Terraform state within the `painting.this` definition.

```
data "terraform_remote_state" "bob_ross" {
  count   = var.bob_required ? 1 : 0
  backend = "remote"
  config = {
    organization = "JamieCo"
    workspaces = {
      name = "bob_ross_painter"
    }
  }
}

resource "painting" "this" {
    objects = var.bob_required ? [data.terraform_remote_state.bob_ross.outputs.happy_little_tree] : []
}
```
The state json will look something like this, note the value in the dependencies list.
```
{
    "version": 4,
    "terraform_version": "1.2.1",
    "serial": 1,
    "lineage": "d08f55c8-bf62-4552-a728-1e86f98500c3",
    "resources": [
        {
            "mode": "managed",
            "type": "painting",
            "name": "this",
            "provider": "provider[\"registry.terraform.io/jamie/bob_ross_painting\"]",
            "instances": [
                {
                    "schema_version": 0,
                    "attributes": {
                        "objects": []
                    },
                    "sensitive_attributes": [],
                    "private": "xXXXxX==",
                    "dependencies": [
                        "data.terraform_remote_state.bob_ross"
                    ]
                }
            ]
        }
    ]
}
```
