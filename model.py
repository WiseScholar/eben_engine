import torch
import torch.nn as nn

class NeuralNet(nn.Module):
    def __init__(self, input_size, hidden_size, num_classes):
        super(NeuralNet, self).__init__()
        # Layer 1: Input layer
        self.l1 = nn.Linear(input_size, hidden_size) 
        # Layer 2: Hidden "thinking" layer
        self.l2 = nn.Linear(hidden_size, hidden_size) 
        # Layer 3: Output layer (number of intents)
        self.l3 = nn.Linear(hidden_size, num_classes)
        # Activation function to introduce non-linearity (helps it learn complex patterns)
        self.relu = nn.ReLU()
    
    def forward(self, x):
        out = self.l1(x)
        out = self.relu(out)
        out = self.l2(out)
        out = self.relu(out)
        out = self.l3(out)
        # We don't need a final activation function here because PyTorch's 
        # CrossEntropyLoss automatically applies it for us during training.
        return out