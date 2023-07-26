# Janeway CDL Utils

A janeway plugin that contains management commands used by cdl staff

## Management commands

* `add_licenses_by_issue <journal_code> <import_file>` - Adds cc license information to a given journal from a jschol export. You can create the expected input file with the following query to the jschol DB `SELECT volume, issue, attrs->>'$.rights' as rights FROM issues WHERE unit_id = 'journal_code'`;
* `delete_journal <journal_code> (--dry-run) (--no-prompt)` - Deletes the journal including articles, files and file histories and removes associated files from storage.  `--dry-run` will print output without actually deleting anything.  `--no-prompt` will run the command without confirming, used for testing *not recommended for command line use*
* `duplicate_last_names`
* `import_earth`
* `import_eer`
* `import_plos2EA`
* `janeway_version`
* `missing_workflowlogs_report`
* `move_preprints <active-user> <proxy-user>` - Merges metadata associated with a proxy user into a specified user account.  This account may be actived or not but it should be one that could be activated in the future.
