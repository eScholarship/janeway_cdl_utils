# Janeway CDL Utils

A janeway plugin that contains management commands used by cdl staff

See also: [janeway_ezid_plugin](https://github.com/eScholarship/janeway_ezid_plugin)

## Management commands

* `add_licenses_by_issue <journal_code> <import_file>` - Adds cc license information to a given journal from a jschol export. You can create the expected input file with the following query to the jschol DB `SELECT volume, issue, attrs->>'$.rights' as rights FROM issues WHERE unit_id = 'journal_code'`;
* `add_preprint_authors <preprint_id> <import_file> (--overwrite)` - Add preprint authors defined in a csv to the given preprint.  By default authors are appended to the existing author list. If `--overwrite` is used delete existing authors first then add authors in file.  File should have the headings: `Preprint ID,Author Order,First Name,Middle Name,Last Name,Email,Affiliation`. Preprint ID is optional but if given it should match the preprint id given as an input.
* `delete_journal <journal_code> (--dry-run) (--no-prompt)` - Deletes the journal including articles, files and file histories and removes associated files from storage.  `--dry-run` will print output without actually deleting anything.  `--no-prompt` will run the command without confirming, used for testing *not recommended for command line use*
* `duplicate_last_names`
* `import_earth`
* `import_eer`
* `import_plos2EA`
* `janeway_version`
* `missing_workflowlogs_report`
* `move_preprints <active-user> <proxy-user>` - Merges metadata associated with a proxy user into a specified user account.  This account may be actived or not but it should be one that could be activated in the future.
* `no_arks <journal-code>` - Reports published articles in a given journal that don't have an associated eScholarship ark
* `no_correspondence_author <journal-code>` - Reports articles in a given journal that don't have a correspondence author
* `push_db_metrics (--profile <aws_profile_name>)` - Pushes current journal, article and file counts to AWS CloudWatch metrics.  You may optionally provide a profile name or if you are using an IAM role you can add it in the settings file as METRICS_ROLE.
* `push_sentry_metrics (--profile <aws_profile_name> --daysago <number>)` - Push the average transaction time for a 24 hour period by default the previous 24 hour period but you may optionally provide a number of days ago to push previous data.  AWS authentication is the same as for `push_db_metrics`.

* `add_publisherdoi_by_preprintdoi <import_file>` - Add published dois to preprints by preprint dois. The import file is expected to be a comma separated csv with the heading: `journal DOI, preprint DOI`. The dois in the import file are expected to start with `https://doi.org`.

## Disable Login

In order to disable logins you can add the DisableLoginMiddleware to the middleware section of the settings.

```
'plugins.cdl_utils.middleware.DisableLoginMiddleware',
```

And add the disable login setting set to true:

```
DISABLE_LOGIN = False
```

## Tests

The test suite can be run in the context of a janeway development environment.  The general command (assuming the plugin is installed in a directory called 'cdl_utils'):

```
python src/manage.py test cdl_utils
```

If you are using a lando development environment:
```
lando manage test cdl_utils
```
