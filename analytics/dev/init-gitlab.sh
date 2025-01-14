#!/bin/bash
set -euo pipefail

# Wait for gitlab to be up
echo "Waiting for GitLab..."
until curl -s -f -o /dev/null "http://localhost:8080"
do
    sleep 5
done
echo "Done."

# Set root user password + create a personal access token for it
PERSONAL_ACCESS_TOKEN="insecure_token"
docker compose exec gitlab gitlab-rails runner "  \
    print 'Updating root user password...'; \
    user = User.find_by(username: 'root');                  \
    user.password = user.password_confirmation = 'deadbeef'; \
    user.save!; \
    puts ' done'; \
    print 'Creating personal access token...'; \
    token = User.find_by_username('root').personal_access_tokens.create( \
        scopes: [:api], \
        name: 'Docker admin token', \
        expires_at: 365.days.from_now, \
    ); \
    token.set_token('$PERSONAL_ACCESS_TOKEN'); \
    token.save!; \
    puts ' done';"

# Create a new runner via the GitLab API and save its token
RUNNER_TOKEN=$(docker compose exec gitlab curl \
    --silent \
    --request POST \
    --url "http://localhost/api/v4/user/runners" \
    --data "runner_type=instance_type" \
    --data "description=test" \
    --data "tag_list=spack,service,small,protected,public,medium,x86_64_v3" \
    --header "PRIVATE-TOKEN: $PERSONAL_ACCESS_TOKEN" | jq -r '.token')

# Register the containerized gitlab runner using the previously acquired token
docker compose exec gitlab-runner gitlab-runner register \
  --non-interactive \
  --description "docker-runner" \
  --url "http://gitlab/" \
  --token "$RUNNER_TOKEN" \
  --executor "docker" \
  --docker-volumes=/var/run/docker.sock:/var/run/docker.sock \
  --docker-image=docker:20-dind

# Create a new project
docker compose exec gitlab curl \
    --request POST \
    --url "http://localhost/api/v4/projects" \
    --header "PRIVATE-TOKEN: $PERSONAL_ACCESS_TOKEN" \
    --header "Content-Type: application/json" \
    --data '{"name": "spack", "path": "spack"}'

# Push spack github repo to the new project
docker compose exec gitlab bash -c " \
    git clone https://github.com/spack/spack.git && \
    cd spack && \
    git remote add gitlab http://root:deadbeef@localhost/root/spack.git && \
    git push -u gitlab develop"
