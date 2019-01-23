# fetch-bill-statuses

Code that ingests XML GPO Bill Status files and massages them into a database back-end. Also serves up the API used by [Members by Interest](https://esperr.github.io/members-by-interest/).

Runs on Google App Engine, so the code is *really* idiosyncratic in parts (i.e., still in 2.7 instead of 3, etc.).
