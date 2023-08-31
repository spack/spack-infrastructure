# Django Analytics App

This is the Django app responsible for managing the analytics postgres database. This database contains any information that we'd like to keep track of in a relational way, but separate from the production gitlab database, as to not interfere with anything.


# Local Setup

To get a local version of the database, simply run the command:
```
docker-compose up
```

Then follow the "Applying Migrations" step to initially setup the database.


## Creating migrations

After modifying the models (db tables), you must create migrations, so that the changes can be applied to the actual database. To do this, run the command:
```
./manage.py makemigrations analytics
```

## Applying migrations

To apply the migrations to the database, run the command:
```
./manage.py migrate
```

**NOTE:** This is done as a part of CI, and so shouldn't normally be run against the production database.


## Accessing Data

To access and/or modify any data within the database, the django shell can be used as follows:
```
./manage.py shell_plus
```

This command will drop you into a Python shell with Django pre-loaded, so that models and data can be viewed, created, deleted, etc.


If you'd like to access postgres more directly, that can be done with the following command:
```
./manage.py dbshell
```

This command will drop you into a psql shell, in the correct database.
