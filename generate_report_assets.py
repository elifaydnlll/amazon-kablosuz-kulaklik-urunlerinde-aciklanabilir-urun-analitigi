import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
import shap
import json

ASSETS = "report_assets"

reviews = pd.read_csv("AllProductReviews.csv")
products = pd.read_csv("ProductInfo.csv")

df = reviews.merge(products, left_on="Product", right_on="ProductShortName", how="left")

analyzer = SentimentIntensityAnalyzer()

df["DiscountRate"] = ((df["MRP"] - df["Price"]) / df["MRP"]) * 100
df["Satisfied"] = (df["ReviewStar"] >= 4).astype(int)
df["ReviewLength"] = df["ReviewBody"].astype(str).apply(len)
df["SentimentScore"] = df["ReviewBody"].astype(str).apply(lambda x: analyzer.polarity_scores(x)["compound"])

def sentiment_label(score):
    if score >= 0.05:
        return "Positive"
    elif score <= -0.05:
        return "Negative"
    else:
        return "Neutral"

df["SentimentLabel"] = df["SentimentScore"].apply(sentiment_label)

def complaint_category(text):
    text = str(text).lower()
    if any(w in text for w in ["battery", "charge", "charging", "backup"]):
        return "Battery"
    elif any(w in text for w in ["connect", "connection", "pair", "bluetooth"]):
        return "Connectivity"
    elif any(w in text for w in ["sound", "bass", "audio", "music"]):
        return "Sound"
    elif any(w in text for w in ["comfort", "fit", "ear", "wear"]):
        return "Comfort"
    elif any(w in text for w in ["mic", "call", "calling", "voice"]):
        return "Mic"
    elif any(w in text for w in ["break", "broken", "durable", "quality"]):
        return "Durability"
    elif any(w in text for w in ["price", "cost", "expensive", "worth"]):
        return "Price"
    else:
        return "Other"

df["ComplaintCategory"] = df["ReviewBody"].apply(complaint_category)

sns.set_style("whitegrid")

# 1. Star distribution
plt.figure(figsize=(6, 3.5))
df["ReviewStar"].value_counts().sort_index().plot(kind="bar", color="#2E5EAA")
plt.title("Yıldız Puanı Dağılımı")
plt.xlabel("Yıldız")
plt.ylabel("Yorum Sayısı")
plt.tight_layout()
plt.savefig(f"{ASSETS}/01_star_distribution.png", dpi=150)
plt.close()

# 2. Correlation heatmap
plt.figure(figsize=(5.5, 4.5))
corr_matrix = df[["ReviewStar", "DiscountRate", "ReviewLength", "SentimentScore", "Satisfied"]].corr()
sns.heatmap(corr_matrix, annot=True, cmap="coolwarm", fmt=".2f")
plt.title("Korelasyon Matrisi")
plt.tight_layout()
plt.savefig(f"{ASSETS}/02_correlation_heatmap.png", dpi=150)
plt.close()

# 3. Complaint category distribution
plt.figure(figsize=(6, 3.5))
df["ComplaintCategory"].value_counts().plot(kind="bar", color="#D9822B")
plt.title("Şikayet Kategorisi Dağılımı")
plt.xlabel("Kategori")
plt.ylabel("Yorum Sayısı")
plt.tight_layout()
plt.savefig(f"{ASSETS}/03_complaint_category.png", dpi=150)
plt.close()

# 4. Category satisfaction
category_satisfaction = pd.crosstab(df["ComplaintCategory"], df["Satisfied"], normalize="index") * 100
category_satisfaction.columns = ["NotSatisfied%", "Satisfied%"]
category_satisfaction = category_satisfaction.sort_values(by="NotSatisfied%", ascending=False)

plt.figure(figsize=(6, 3.5))
category_satisfaction["NotSatisfied%"].plot(kind="bar", color="#C0392B")
plt.title("Kategori Bazlı Memnuniyetsizlik Oranı (%)")
plt.xlabel("Şikayet Kategorisi")
plt.ylabel("Memnun Olmayan Oranı (%)")
plt.tight_layout()
plt.savefig(f"{ASSETS}/04_category_satisfaction.png", dpi=150)
plt.close()

# 5. Product summary
product_summary = df.groupby("Product").agg(
    review_count=("ReviewStar", "count"),
    avg_rating=("ReviewStar", "mean"),
    price=("Price", "first"),
    mrp=("MRP", "first"),
).sort_values(by="review_count", ascending=False)

# 6. Model
features = ["Price", "MRP", "DiscountRate", "ReviewLength", "SentimentScore", "ComplaintCategory", "Product"]
X = df[features]
y = df["Satisfied"]

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

categorical_features = ["ComplaintCategory", "Product"]
numeric_features = ["Price", "MRP", "DiscountRate", "ReviewLength", "SentimentScore"]

preprocessor = ColumnTransformer(transformers=[
    ("cat", OneHotEncoder(handle_unknown="ignore"), categorical_features),
    ("num", "passthrough", numeric_features),
])

model = Pipeline(steps=[
    ("preprocessor", preprocessor),
    ("classifier", RandomForestClassifier(n_estimators=200, random_state=42, class_weight="balanced")),
])

model.fit(X_train, y_train)
y_pred = model.predict(X_test)

acc = accuracy_score(y_test, y_pred)
cm = confusion_matrix(y_test, y_pred)
report_dict = classification_report(y_test, y_pred, output_dict=True)

# Confusion matrix plot
plt.figure(figsize=(4.5, 4))
sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", xticklabels=["Memnun Değil", "Memnun"], yticklabels=["Memnun Değil", "Memnun"])
plt.title("Karmaşıklık Matrisi (Test Seti)")
plt.xlabel("Tahmin")
plt.ylabel("Gerçek")
plt.tight_layout()
plt.savefig(f"{ASSETS}/05_confusion_matrix.png", dpi=150)
plt.close()

# 7. SHAP
X_test_transformed = model.named_steps["preprocessor"].transform(X_test)
feature_names = model.named_steps["preprocessor"].get_feature_names_out()
rf_model = model.named_steps["classifier"]

explainer = shap.TreeExplainer(rf_model)
X_sample = X_test_transformed[:500]
shap_values = explainer.shap_values(X_sample)

if len(np.array(shap_values).shape) == 3:
    shap_values_class1 = shap_values[:, :, 1]
else:
    shap_values_class1 = shap_values[1]

plt.figure(figsize=(7, 5))
shap.summary_plot(shap_values_class1, X_sample, feature_names=feature_names, show=False, max_display=12)
plt.tight_layout()
plt.savefig(f"{ASSETS}/06_shap_summary.png", dpi=150, bbox_inches="tight")
plt.close()

# Mean absolute SHAP importance table
mean_abs_shap = np.abs(shap_values_class1).mean(axis=0)
shap_importance = pd.Series(mean_abs_shap, index=feature_names).sort_values(ascending=False).head(10)

# 8. Financial simulation
mic_df = df[df["ComplaintCategory"] == "Mic"]
mic_reviews = len(mic_df)
mic_not_satisfied_rate = 1 - mic_df["Satisfied"].mean()

monthly_visitors = 100000
current_conversion_rate = 0.03
improved_conversion_rate = 0.037
average_price = df["Price"].mean()
profit_margin = 0.25
development_cost = 100000

current_sales = monthly_visitors * current_conversion_rate
improved_sales = monthly_visitors * improved_conversion_rate
additional_sales = improved_sales - current_sales

profit_per_unit = average_price * profit_margin
additional_profit = additional_sales * profit_per_unit
net_profit = additional_profit - development_cost
roi = (net_profit / development_cost) * 100

results = {
    "shape_reviews": list(reviews.shape),
    "shape_products": list(products.shape),
    "merged_shape": list(df.shape),
    "satisfied_pct": float(df["Satisfied"].mean() * 100),
    "sentiment_counts": df["SentimentLabel"].value_counts().to_dict(),
    "complaint_counts": df["ComplaintCategory"].value_counts().to_dict(),
    "category_satisfaction": category_satisfaction.round(2).to_dict(orient="index"),
    "product_summary": product_summary.round(2).reset_index().to_dict(orient="records"),
    "corr_matrix": corr_matrix.round(3).to_dict(),
    "accuracy": float(acc),
    "confusion_matrix": cm.tolist(),
    "classification_report": report_dict,
    "shap_importance_top10": shap_importance.round(4).to_dict(),
    "mic_reviews": int(mic_reviews),
    "mic_not_satisfied_rate": float(mic_not_satisfied_rate),
    "average_price": float(average_price),
    "current_sales": float(current_sales),
    "improved_sales": float(improved_sales),
    "additional_sales": float(additional_sales),
    "profit_per_unit": float(profit_per_unit),
    "additional_profit": float(additional_profit),
    "development_cost": development_cost,
    "net_profit": float(net_profit),
    "roi_pct": float(roi),
}

with open(f"{ASSETS}/results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print("DONE")
print(json.dumps(results, ensure_ascii=False, indent=2))
