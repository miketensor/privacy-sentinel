# streamlit_app.py
import streamlit as st
import requests
import json
from privacy_sentinel import run_privacy_logic  # Import direct du fichier local

st.set_page_config(page_title="Privacy Sentinel Demo", page_icon="🔒")

st.title("🔒 Privacy Sentinel - Demo")
st.markdown("**Protégez vos données sensibles lors d'appels aux LLM**")

# Sidebar avec configuration
with st.sidebar:
    st.header("⚙️ Configuration")
    
    model = st.selectbox(
        "Modèle Groq",
        ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"] #, "mixtral-8x7b-32768"]
    )
    temperature = st.slider("Température", 0.0, 1.0, 0.7)
    
    st.markdown("---")
    st.markdown("### 📊 Statistiques")
    if 'total_requests' not in st.session_state:
        st.session_state.total_requests = 0
    st.metric("Requêtes traitées", st.session_state.total_requests)

# Exemples prédéfinis
st.subheader("💡 Exemples de prompts avec PII")
examples = {
    "Bancaire 🏦": "Mon client Jean Dupont (jean.dupont@banque.fr) souhaite un prêt immobilier de 250 000€. Sa carte bancaire 4532-1234-5678-9012 expire le 08/26. Comment procéder ?",
    "Santé 🏥": "La patiente Marie Martin, née le 15/03/1980, NIR 2 80 03 75 123 456 78, présente des symptômes de diabète de type 2. Quel suivi recommandez-vous ?",
    "RH 👔": "Candidat Pierre Blanc, tél 06 12 34 56 78, email pierre.blanc@gmail.com, habitant 12 rue de la Paix 75001 Paris, salaire actuel 65k€. Évaluation du profil ?",
    "Support Client 📞": "Le client au 01 42 85 63 21 signale un problème avec sa commande. Son email: client@example.com. IP de connexion: 192.168.1.100"
}

selected_example = st.selectbox("Choisir un exemple", [""] + list(examples.keys()))

# Zone de saisie
prompt = st.text_area(
    "Votre prompt (peut contenir des données sensibles)",
    value=examples.get(selected_example, ""),
    height=150,
    placeholder="Tapez votre question contenant des données personnelles..."
)

if st.button("🚀 Envoyer via Privacy Sentinel", type="primary"):
    if not prompt:
        st.warning("Veuillez saisir un prompt")
    else:
        with st.spinner("Traitement en cours..."):
            try:
                data = run_privacy_logic(prompt, model, temperature)
                    
                # Affichage des résultats
                st.success("✅ Traitement réussi !")
                
                # Tabs pour organiser l'affichage
                tab1, tab2, tab3, tab4 = st.tabs(["📊 Résultat", "🔍 PII Détectées", "🔒 Anonymisation", "📝 Détails"])
                
                with tab1:
                    st.subheader("Réponse finale")
                    st.info(data['final_response'])
                
                with tab2:
                    st.subheader(f"🎯 {len(data['pii_detected'])} données sensibles détectées")
                    if data['pii_detected']:
                        for pii in data['pii_detected']:
                            st.markdown(f"- **{pii['type']}**: `{pii['text']}` (confiance: {pii['score']})")
                    else:
                        st.success("Aucune donnée sensible détectée")
                
                with tab3:
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("**Prompt original**")
                        st.code(data['original_prompt'], language="text")
                    with col2:
                        st.markdown("**Prompt anonymisé envoyé au LLM**")
                        st.code(data['anonymized_prompt'], language="text")
                
                with tab4:
                    st.json(data)
                    
            except Exception as e:
                st.error(f"❌ Erreur: {str(e)}")

# Footer
st.markdown("---")
st.markdown("🔒 **Privacy Sentinel** - Propulsé par Presidio + Groq | Gratuit & Open Source")