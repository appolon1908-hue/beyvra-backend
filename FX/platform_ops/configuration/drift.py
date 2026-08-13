import hashlib,json
SENSITIVE={"SECRET","CREDENTIAL","TOKEN","PRIVATE_KEY"}
def normalized_hash(values):return hashlib.sha256(json.dumps(values,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
class ConfigurationDriftService:
    @staticmethod
    def compare(declared,runtime):
        keys=sorted(set(declared)|set(runtime)); drift=[k for k in keys if declared.get(k)!=runtime.get(k)]
        return {"state":"NONE" if not drift else "DRIFT","keys":drift,"declared_hash":normalized_hash(declared),"runtime_hash":normalized_hash(runtime)}
def safe_definition(definition):return {"name":definition.key,"state":definition.status,"source":"registry","sensitivity":definition.sensitivity,"version":definition.version}
