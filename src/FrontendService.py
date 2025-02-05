import re
from urllib.parse import urlparse

from Util import setup_logger
from NLPUtil import split_with_delimiters, get_longest_common_word_sequences

logger = setup_logger('FootnoteService')


class FrontendService:
    def __init__(self, config, response_text, gpt_input_text_df):
        self.config = config
        self.response_text = response_text
        used_columns = ['docno', 'name', 'url', 'url_id', 'text', 'len_text', 'in_scope']  # TODO: add url_id
        self.gpt_input_text_df = gpt_input_text_df[used_columns]

    def get_data_json(self, response_text, gpt_input_text_df):
        def create_response_json_object(text, type):
            return {"text": text, "type": type}

        def create_source_json_object(footnote, domain, url, title, text):
            return {"footnote": footnote, "domain": domain, "url": url, "title": title, "text": text}

        def reorder_url_id(response_text, gpt_input_text_df):
            # response_text: find reference in text & re-order
            url_id_list = [int(x) for x in dict.fromkeys(re.findall(r'\[([0-9]+)\]', response_text))]
            url_id_map = dict(zip(url_id_list, range(1, len(url_id_list) + 1)))

            for url_id, new_url_id in url_id_map.items():
                response_text = response_text.replace(f'[{url_id}]', f'[{new_url_id}]')

            # gpt_input_text_df: find reference in text & re-order
            in_scope_source_df = gpt_input_text_df[gpt_input_text_df['url_id'].isin(url_id_map.keys()) & gpt_input_text_df['in_scope']].copy()
            in_scope_source_df['url_id'] = in_scope_source_df['url_id'].map(url_id_map)
            return response_text, in_scope_source_df

        def get_response_json(response_text):
            def create_response_json_object(text, type):
                return {"text": text, "type": type}

            response_json = []
            split_sentence = re.findall(r'\[[0-9]+\]|[^\[\]]+', response_text)

            components = []
            for component in split_sentence:
                components.extend(split_with_delimiters(component, ['\n']))
            for sentence in components:
                if sentence.startswith('[') and sentence.endswith(']'):
                    response_json.append(create_response_json_object(sentence, "footnote"))
                elif sentence == '\n':
                    response_json.append(create_response_json_object(sentence, "newline"))
                else:
                    response_json.append(create_response_json_object(sentence, "response"))
            return response_json

        def get_source_json(in_scope_source_df):
            in_scope_source_df.loc[:, 'docno'] = in_scope_source_df['docno'].astype(int)
            in_scope_source_df.sort_values('docno', inplace=True)
            source_text_list = []
            source_json = []
            source_url_df = in_scope_source_df[['url_id', 'url', 'name', 'snippet']].drop_duplicates().sort_values('url_id').reset_index(drop=True)
            for index, row in source_url_df.iterrows():
                url_text = ''
                url_text += f"[{row['url_id']}] {row['url']}\n"

                for index, row in in_scope_source_df[in_scope_source_df['url_id'] == row['url_id']].iterrows():
                    url_text += f"  {row['text']}\n"

                source_text_list.append(url_text)

                domain_name = urlparse(row['url']).netloc.replace('www.', '')
                source_json.append(create_source_json_object(f"[{row['url_id']}]", domain_name, row['url'], row['name'], row['snippet']))
            source_text = ''.join(sorted(source_text_list))

            source_json = sorted(source_json, key=lambda x: x['footnote'])
            return source_json, source_text

        def get_explainability_json(response_text, source_text):
            def get_colors():
                return ['#ffe3e8', '#f1e1ff', '#c5d5ff', '#c5efff', '#d6fffa', '#e7ffe7', '#f7ffa7', '#fff3b3', '#ffdfdf', '#ffcaca']

            def create_response_json_object(text, type, color):
                return {"text": text, "type": type, "color": color}

            def get_explain_json(text, word_color_dict):
                common_word_sequences = list(word_color_dict.keys())
                word_list = split_with_delimiters(text.lower(), common_word_sequences + ['\n'])
                explain_json = []
                for word in word_list:
                    if word == '\n':
                        explain_json.append(create_response_json_object(word, "newline", ""))
                    elif word.lower() in common_word_sequences:
                        explain_json.append(create_response_json_object(word, "keyword", word_color_dict[word.lower()]))
                    else:
                        explain_json.append(create_response_json_object(word, "word", ""))
                return explain_json

            longest_common_word_sequences = get_longest_common_word_sequences(response_text, source_text, k=10)
            word_color_dict = {longest_common_word_sequences[i]: get_colors()[i] for i in range(min(len(longest_common_word_sequences), len(get_colors())))}

            response_explain_json = get_explain_json(response_text, word_color_dict)
            source_explain_json = get_explain_json(source_text, word_color_dict)
            return response_explain_json, source_explain_json

        response_text, in_scope_source_df = reorder_url_id(response_text, gpt_input_text_df)
        response_json = get_response_json(response_text)
        source_json, source_text = get_source_json(in_scope_source_df)
        response_explain_json, source_explain_json = get_explainability_json(response_text, source_text)

        return source_text, {'response_json': response_json,
                             'source_json': source_json,
                             'response_explain_json': response_explain_json,
                             'source_explain_json': source_explain_json
                             }

# if __name__ == '__main__':
#     obj = get_response_json('Local School [1] [2].\n Dani [3]')
#     print(obj)
