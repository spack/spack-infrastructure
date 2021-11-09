# Note on gitlab_ro_user_job.yaml

Metabase requires a user to connect to the database. Best practice is to have this be a read only user on the database.  the `gitlab_ro_user_job.yaml` contains yaml to idemopotently create this user and set appropriate permissions. **It should not need to be run.** It is maintained here for reproducibility in the case that the gitlab postgresql database get hosed for some reason. 

## Running the Job
To run the job:

``` sh
kubectl apply -f gitlab_ro_user_job.yml
```

Once complete clean up the Job

``` sh
kubeclt delete job -n gitlab job-create-ro-gitlab-postgres-user
```

## Note on Secrets

Note that this job requires there to be a `gitlab-ro-postgresql-password` secret in the gitlab namespace.  This should have a single key `postgresql-gitlab-ro-user-password`. See the secrets.yaml file for an example of how this is defined.
