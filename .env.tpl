# provide the host where the nova api is running (e.g. your virtual dev instance)
WANDELAPI_BASE_URL="{{ .InstanceInformation.NovaApiHost }}"
CELL_ID="cell"
LOG_LEVEL=info

###
# SECRETS
#
# These should never be defined in the .env file, only in the gitignored .env.local or 
# in the environment variables of the deployment.
###

# For basic auth with the API
NOVA_USERNAME="{{ .InstanceInformation.BasicAuth.Username }}"
NOVA_PASSWORD="{{ .InstanceInformation.BasicAuth.Password }}"