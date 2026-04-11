import pandas as pd
from sklearn.linear_model import LinearRegression

# Load dataset
data = pd.read_csv('data/data.csv')

# Features and target
X = data[['risk', 'years', 'amount']]
y = data['returns']

# Train model
model = LinearRegression()
model.fit(X, y)

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
print("Predicted Total Returns:", round(predicted_return, 2))

print("\n--- Investment Scores ---")
for k, v in scores.items():
    print(k, ":", round(v, 2))

print("\nRecommended Investment:", recommended)
print("Reason:", reason)