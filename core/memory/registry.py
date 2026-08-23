class MemoryRegistry:
    def __init__(self):
        self._memories = {}
        self._default_name = None

    def register(self, memory):
        if memory.name in self._memories:
            raise ValueError(f"Memory already registered: {memory.name}")
        self._memories[memory.name] = memory
        if self._default_name is None:
            self._default_name = memory.name

    def get(self, name=None):
        name = name or self._default_name
        if name is None or name not in self._memories:
            raise KeyError(f"Memory not found: {name}")
        return self._memories[name]

    def describe_memories(self):
        return [{"name": item.name, "description": item.description} for item in self._memories.values()]
