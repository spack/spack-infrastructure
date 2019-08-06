### Key Points for Spack Build Pipeline Setup

#### GPG Key for Signing Packages

- Key Generation Example
```bash
cat gpg-script.txt
```
```
%echo Generating a basic OpenPGP key
Key-Type: RSA
Key-Length: 2048
Subkey-Type: RSA
Subkey-Length: 2048
Name-Real: Spack Build Pipeline
Name-Comment: Demo Key
Name-Email: key@spack.demo
Expire-Date: 0
%commit
%echo done
```

```bash
email="key@spack.demo"

gpg --batch                                  \
    --gen-key                                \
    --pinentry-mode=loopback --passphrase "" \
    ./gpg-script.txt

awk='/^ +[A-F0-9]+$/{key=$1}'
awk="${awk}/$email/{print key}"
keyid="$( gpg --list-keys | awk "$awk" )"

(
    gpg --export --armor "$keyid" \
 && gpg --export-secret-keys --armor "$keyid"
) | base64 | tr -d '\n' > ./package-signing-key
```

#### CDash Instance
 - Authentication Token

#### Gitlab Instance
 - Gitlab Runners
    - Tags
        - Must have at least one runner with "spack-pre-ci" tag.
        - Must have at least one runner with "spack-post-ci" tag.
        - You likely want to include other tags so you can target
          them in your `spack.yaml` file.
        - None of these tags are mutually-exclusive; you can have
          a single runner with all these tags, if you prefer.
    - Runners can use any executor; they don't have to run
      docker containers!
        - As long as jobs run in a suitable environment.
            - Necessary compilers installed and ready to use
              (bootstrapped compilers notwithstanding).
            - Mirrors prepared and accessable using the same URI.
                - For example: `file///path/to/my/mirror` must resolve
                  to the same mirror -- backed by the same underlying
                  storage -- for every job.
    - Projects/Repositories
        - spack-mirror: mirror of spack
            - Should not have any protected branches.  Must accept
              force-pushed branches from upstream.
            - CI/CD Settings
                - "git fetch" strategy (Optional)
                - "Git shallow clone" setting = 1 (Optional)
                - Variables:
                    - CDASH_AUTH_TOKEN: CDash authentication token.
                    - DOWNSTREAM_CI_REPO: URL for downstream repo.
                        - Should be "spack-build" repo.  `pre-ci` jobs must
                          have read and write access via this URL.
                    - SPACK_RELEASE_ENVIRONMENT_REPO: URL for environment
                      repo (containing your `spack.yaml` file).  `pre-ci`
                      jobs must have read access via this URL.
                    - SPACK_RELEASE_ENVIRONMENT_PATH: relative path from
                      the root of the `SPACK_RELEASE_ENVIRONMENT_REPO` to
                      the directory containing your `spack.yaml` file.
        - spack-build: internal repo that accepts pushes from pre-ci.
            - Should not have any protected branches.  Must accept
              force-pushed branches from `spack-mirror`.
            - CI/CD Settings
                - "git fetch" strategy (Optional)
                - "Git shallow clone" setting = 1 (Optional)
                - Variables:
                    - SPACK_SIGNING_KEY: GPG key for signing packages.
        - spack-env: site-specific spack environments

#### Known Issues

 - The pre-ci phase cannot report build group information to a private CDash
   project.
 - Build jobs in the primary build phase cannot submit authenticated CDash
   reports.
 - Installing packages from a binary mirror may fail if the fetched
   binary needs to be relocated.
 - Under certain conditions, the pre-ci phase may fail to clone a spack
   environment repo and/or fail to push to the downstream repo.
 - There is a known issue preventing package builds from using a compiler that
   was previously bootstrapped.
 - Gitlab-wide settings may need to be adjusted to increase limits on job
   run time and/or job artifact size, depending on the packages being built.

