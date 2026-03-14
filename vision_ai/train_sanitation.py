import torch
import torch.nn as nn
import torch.optim as optim
from torchvision import datasets, transforms, models
import os
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.join(BASE_DIR, "dataset")
MODEL_PATH = os.path.join(BASE_DIR, "sanitation_model.pth")
INDICES_PATH = os.path.join(BASE_DIR, 'class_indices.json')

IMG_SIZE = 224
BATCH_SIZE = 8
EPOCHS = 10

def create_folders():
    categories = ['clean', 'trash_outside_bin', 'clogged_sink', 'floor_waste']
    for cat in categories:
        path = os.path.join(DATASET_DIR, cat)
        os.makedirs(path, exist_ok=True)
    print(f"Dataset folders created at {DATASET_DIR}.")
    print("Please add image files to these folders before running this script again to train.")

def main():
    if not os.path.exists(DATASET_DIR):
        create_folders()
        return

    # Check if there are images
    has_images = False
    for root, dirs, files in os.walk(DATASET_DIR):
        for file in files:
            if file.lower().endswith(('png', 'jpg', 'jpeg')):
                has_images = True
                break
    
    if not has_images:
        print("No images found in the dataset directories! Please add images and run again.")
        create_folders()
        return

    print("Setting up data transforms...")
    data_transforms = transforms.Compose([
        transforms.Resize((IMG_SIZE, IMG_SIZE)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(20),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])

    dataset = datasets.ImageFolder(DATASET_DIR, transform=data_transforms)
    
    if len(dataset) == 0:
        print("Not enough images to train. Please add more images to each folder.")
        return

    # Split dataset into train and val (80/20)
    train_size = int(0.8 * len(dataset))
    val_size = len(dataset) - train_size
    train_dataset, val_dataset = torch.utils.data.random_split(dataset, [train_size, val_size])

    train_loader = torch.utils.data.DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True)
    val_loader = torch.utils.data.DataLoader(val_dataset, batch_size=BATCH_SIZE, shuffle=False)

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    print("Loading MobileNetV2 base model...")
    model = models.mobilenet_v2(weights=models.MobileNet_V2_Weights.IMAGENET1K_V1)
    
    # Freeze base parameters
    for param in model.parameters():
        param.requires_grad = False

    # Replace classifier
    num_ftrs = model.classifier[1].in_features
    model.classifier[1] = nn.Sequential(
        nn.Linear(num_ftrs, 128),
        nn.ReLU(),
        nn.Linear(128, len(dataset.classes))
    )

    model = model.to(device)

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.classifier.parameters(), lr=0.001)

    print("Starting training...")
    for epoch in range(EPOCHS):
        model.train()
        running_loss = 0.0
        running_corrects = 0

        for inputs, labels in train_loader:
            inputs = inputs.to(device)
            labels = labels.to(device)

            optimizer.zero_grad()
            outputs = model(inputs)
            _, preds = torch.max(outputs, 1)
            loss = criterion(outputs, labels)

            loss.backward()
            optimizer.step()

            running_loss += loss.item() * inputs.size(0)
            running_corrects += torch.sum(preds == labels.data)

        epoch_loss = running_loss / train_size if train_size > 0 else 0
        epoch_acc = running_corrects.double() / train_size if train_size > 0 else 0
        
        print(f'Epoch {epoch+1}/{EPOCHS} Loss: {epoch_loss:.4f} Acc: {epoch_acc:.4f}')

    # Save class indices
    class_indices = {v: k for k, v in dataset.class_to_idx.items()}
    with open(INDICES_PATH, 'w') as f:
        json.dump(class_indices, f)

    torch.save(model.state_dict(), MODEL_PATH)
    print(f"Model saved to {MODEL_PATH}")

if __name__ == "__main__":
    main()
