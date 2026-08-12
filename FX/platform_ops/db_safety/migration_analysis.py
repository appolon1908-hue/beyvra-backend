CLASSIFIERS={"AddField":"EXPAND","RunPython":"MIGRATE_DATA","RemoveField":"CONTRACT","AddIndex":"INDEX","AddConstraint":"CONSTRAINT","AlterField":"TYPE_CHANGE"}
def classify(operation):return CLASSIFIERS.get(type(operation).__name__,"REVIEW_REQUIRED")
