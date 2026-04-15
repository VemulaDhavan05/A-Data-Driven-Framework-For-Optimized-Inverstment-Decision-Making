import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import r2_score

# Load dataset
data = pd.read_csv('data/data.csv')

# Features (Risk, Years, Capital) and Target (Final Returns)
X = data[['risk', 'years', 'amount']]
y = data['returns']

# Split data: 80% for training, 20% for scientific testing
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# Train upgraded model: Random Forest can handle exponential compounding growth
model = RandomForestRegressor(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

# PROOF: Test the model on unseen data
y_pred = model.predict(X_test)
accuracy = r2_score(y_test, y_pred)

# ===== USER INPUT =====
risk = 3
years = 5
amount = 100000

# Prediction
input_data = pd.DataFrame([[risk, years, amount]], columns=['risk', 'years', 'amount'])
predicted_return = model.predict(input_data)[0]

# ===== SCORING SYSTEM =====

# Scores for each investment type
stock_score = (risk * 2) + (years * 1.5)
mutual_score = (5 - abs(risk - 3)) + years
real_estate_score = (years * 2) + (risk * 0.5)

# Store scores
scores = {
    "Stocks": stock_score,
    "Mutual Funds": mutual_score,
    "Real Estate": real_estate_score
}

# Recommendation
recommended = max(scores, key=scores.get)

# ===== REASONS =====
if recommended == "Stocks":
    reason = "Higher risk tolerance with potential for high returns in shorter duration"
elif recommended == "Mutual Funds":
    reason = "Balanced risk and stable returns suitable for medium-term investment"
else:
    reason = "Long-term investment with asset growth and stable appreciation"

# ===== OUTPUT =====
print("--- MODEL PROOF OF ACCURACY ---")
print(f"Validation Accuracy (R-Squared): {accuracy:.4f}")
print("(A score closer to 1.0 proves the model successfully learned from the dataset)\n")

print("Predicted Total Returns:", round(predicted_return, 2))

print("\n--- Investment Scores ---")
for k, v in scores.items():
    print(k, ":", round(v, 2))

print("\nRecommended Investment:", recommended)
print("Reason:", reason)