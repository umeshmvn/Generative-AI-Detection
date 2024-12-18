from flask import Flask, jsonify, request
from flask_cors import CORS
import torch
import re
from transformers import GPT2LMHeadModel, GPT2TokenizerFast
from collections import OrderedDict

app = Flask(__name__)
CORS(app)

# GPT2PPL class definition
class GPT2PPL:
    def __init__(self, model_id="gpt2"):
        self.model_id = model_id
        self.model = GPT2LMHeadModel.from_pretrained(model_id)
        self.tokenizer = GPT2TokenizerFast.from_pretrained(model_id)
        self.max_length = self.model.config.n_positions
        self.stride = 512

    def getResults(self, threshold):
        if threshold < 60:
            label = 0
            return "The Text is generated by AI.", label
        elif threshold < 80:
            label = 0
            return "The Text most probably contains parts which are generated by AI. (requires more text for better judgment)", label
        else:
            label = 1
            return "The Text is written by a Human.", label

    def __call__(self, sentence):
        results = OrderedDict()
        total_valid_char = re.findall("[a-zA-Z0-9]+", sentence)
        total_valid_char = sum([len(x) for x in total_valid_char])  # finds len of all the valid characters in a sentence
        if total_valid_char < 100:
            return {"status": "Please input more text (minimum 100 characters)"}, "Please input more text (minimum 100 characters)"
        
        lines = re.split(r'(?<=[.?!][ \[\(])|(?<=\n)\s*', sentence)
        lines = list(filter(lambda x: (x is not None) and (len(x) > 0), lines))
        ppl = self.getPPL(sentence)
        results["Perplexity"] = ppl

        Perplexity_per_line = []
        for line in lines:
            if re.search("[a-zA-Z0-9]+", line) is None:
                continue
            ppl = self.getPPL(line)
            Perplexity_per_line.append(ppl)

        results["Perplexity per line"] = sum(Perplexity_per_line) / len(Perplexity_per_line)
        results["Burstiness"] = max(Perplexity_per_line)
        out, label = self.getResults(results["Perplexity per line"])
        results["label"] = label
        return results, out

    def getPPL(self, sentence):
        encodings = self.tokenizer(sentence, return_tensors="pt")
        seq_len = encodings.input_ids.size(1)
        nlls = []
        prev_end_loc = 0

        for begin_loc in range(0, seq_len, self.stride):
            end_loc = min(begin_loc + self.max_length, seq_len)
            trg_len = end_loc - prev_end_loc
            input_ids = encodings.input_ids[:, begin_loc:end_loc]
            target_ids = input_ids.clone()
            target_ids[:, :-trg_len] = -100

            with torch.no_grad():
                outputs = self.model(input_ids, labels=target_ids)
                neg_log_likelihood = outputs.loss * trg_len

            nlls.append(neg_log_likelihood)
            prev_end_loc = end_loc
            if end_loc == seq_len:
                break

        ppl = int(torch.exp(torch.stack(nlls).sum() / end_loc))
        return ppl

# API route to analyze text
@app.route('/', methods=['POST'])
def postData():
    try:
        data = request.get_json()  # Get the JSON payload correctly
        text = data.get('text')
        if not text:
            return jsonify({'error': 'No text provided'}), 400
        # Create an instance of GPT2PPL class
        gpt2ppl = GPT2PPL()
        # Get results by calling the instance
        results, output = gpt2ppl(text)
        return jsonify({"output": output, "results": dict(results)})    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)


# {
#   "output": "The Text is generated by AI.",
#   "results": {
#     "Burstiness": 46,
#     "Perplexity": 18,
#     "Perplexity per line": 34.333333333333336,
#     "label": 0
#   }
# }