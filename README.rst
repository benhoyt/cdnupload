

Example usage:

_keys_by_path = {}

def init_server():
    global _keys_by_path
    _keys_by_path = build_key_map('static/')
    # OR
    _keys_by_path = load_key_map()

    def static_url(rel_path):
        return settings.static_prefix + _keys_by_path[rel_path]
    flask_env.filters['static_url'] = static_url


def save_key_map():
    with open('static_key_map.json', 'w') as f:
        json.dump(f, build_key_map('static/'), sort_keys=True, indent=4)


def load_key_map():
    with open('static_key_map.json') as f:
        return json.load(f)
