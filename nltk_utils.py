import numpy as np
import nltk
from nltk.stem.porter import PorterStemmer

# Initialize the stemmer
stemmer = PorterStemmer()

# Only run this once to download the tokenizer package
nltk.download('punkt') 
nltk.download('punkt_tab') # Might be required depending on your NLTK version

def tokenize(sentence):
    """
    Split sentence into an array of words/tokens.
    A token can be a word, punctuation character, or number.
    """
    return nltk.word_tokenize(sentence)

def stem(word):
    """
    Stemming = finding the root form of the word.
    Example:
    words = ["booking", "books", "booked"]
    stemmed_words = [stem(w) for w in words]
    -> ["book", "book", "book"]
    """
    return stemmer.stem(word.lower())

def bag_of_words(tokenized_sentence, all_words):
    """
    Return an array of 1 or 0 for each word in the vocabulary that exists in the sentence.
    
    Example:
    sentence = ["hello", "how", "are", "you"]
    words = ["hi", "hello", "I", "you", "bye", "thank", "cool"]
    bag   = [  0 ,    1 ,    0 ,   1 ,    0 ,    0 ,      0]
    """
    # Stem each word in the given sentence
    tokenized_sentence = [stem(w) for w in tokenized_sentence]
    
    # Initialize bag with 0 for each word
    bag = np.zeros(len(all_words), dtype=np.float32)
    
    for idx, w in enumerate(all_words):
        if w in tokenized_sentence: 
            bag[idx] = 1.0

    return bag

# --- QUICK TEST BLOCK ---
# If you run this file directly, it will test the functions to make sure they work.
if __name__ == "__main__":
    test_sentence = "How do I book a room?"
    print(f"Original: {test_sentence}")
    
    words = tokenize(test_sentence)
    print(f"Tokenized: {words}")
    
    stemmed_words = [stem(w) for w in words]
    print(f"Stemmed: {stemmed_words}")
    
    # Let's pretend our AI's entire vocabulary is only these 7 words:
    vocab = ["how", "book", "room", "cancel", "fee", "hello", "where"]
    bag = bag_of_words(words, vocab)
    print(f"Bag of Words: {bag}")