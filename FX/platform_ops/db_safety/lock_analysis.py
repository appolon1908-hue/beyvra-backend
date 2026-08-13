def analyze(operation):
    name=type(operation).__name__; risks=[]
    if name in {"RemoveField","AlterField","DeleteModel"}:risks.append("ACCESS_EXCLUSIVE_OR_REWRITE_REVIEW")
    if name=="AddIndex" and not getattr(operation,"concurrently",False):risks.append("BLOCKING_INDEX_REVIEW")
    return risks
