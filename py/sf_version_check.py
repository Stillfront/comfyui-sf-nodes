class SFVersionCheck:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("version",)
    FUNCTION = "get_version"
    CATEGORY = "Stillfront/Utils"

    def get_version(self):
        return ("SF ComfyUI Nodes v1.0.2",)


NODE_CLASS_MAPPINGS = {"SFVersionCheck": SFVersionCheck}
NODE_DISPLAY_NAME_MAPPINGS = {"SFVersionCheck": "SF Version Check"}
