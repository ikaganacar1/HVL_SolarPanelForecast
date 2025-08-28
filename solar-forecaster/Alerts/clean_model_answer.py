import re

def main(full_text: str) -> dict:
    # 1. Remove <details> tags and their content
    cleaned_text = re.sub(r'<details.*?</details>', '', full_text, flags=re.DOTALL)
    
    # 2. Strip leading/trailing whitespace and newlines
    stripped_text = cleaned_text.strip()
    
    # 3. If the text is wrapped in outer quotes, remove them
    if stripped_text.startswith('"') and stripped_text.endswith('"'):
        unquoted_text = stripped_text[1:-1]
    else:
        unquoted_text = stripped_text
    
    # 4. Fix escaped quotes (\\" -> ") and other escape sequences
    final_response = unquoted_text.replace('\\"', '"').replace('\\n', '\n').replace('\\t', '\t')
    
    return {"cleaned_response": final_response}