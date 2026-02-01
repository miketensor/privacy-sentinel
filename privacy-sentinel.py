import tldextract
import os

# 1. Configurer l'extracteur pour être totalement OFFLINE
offline_extractor = tldextract.TLDExtract(
    cache_dir=None,                  # Pas de cache disque
    suffix_list_urls=None,           # Bloque les appels réseau
    fallback_to_snapshot=True        # Utilise la liste intégrée au package
)

# 2. Remplacer l'extracteur par défaut par notre version offline
tldextract.extract = offline_extractor

# 3. Sécurité supplémentaire via les variables d'environnement
os.environ["TLDEXTRACT_SUFFIX_LIST_URLS"] = ""


# Utilisation explicite
# result = tldextractor("example.co.uk")

import uuid
import streamlit as st
from typing import Dict, List
from presidio_analyzer import AnalyzerEngine, RecognizerRegistry, Pattern, PatternRecognizer
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig
from presidio_analyzer.nlp_engine import NlpEngineProvider
from groq import Groq

# from google.colab import userdata
# import os

# # Récupérer la clé depuis les secrets Colab
# os.environ["GROQ_API_KEY"] = userdata.get('GROQ_API_KEY')

# # Ensuite utiliser normalement
# from groq import Groq
# groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))


# load_dotenv() #charger les variables d'environnement depuis un fichier .env dans votre projet.

nlp_configuration = {
    "nlp_engine_name": "spacy",
    "models": [
        {"lang_code": "fr", "model_name": "fr_core_news_md"},
        {"lang_code": "en", "model_name": "en_core_web_sm"}
    ],
}

# 2. Création de l'engine NLP
provider = NlpEngineProvider(nlp_configuration=nlp_configuration)
nlp_engine = provider.create_engine()

# 3. Création du Registre et chargement des recognizers par défaut
registry = RecognizerRegistry()
registry.load_predefined_recognizers(nlp_engine=nlp_engine, languages=["fr", "en"])

# ===== CREATION DES RECOGNIZERS PERSONNALISÉS =====
# Carte bancaire (le problème principal!)
class CreditCardRecognizerFR(PatternRecognizer):
    """Recognizer de carte bancaire pour le français"""
    PATTERNS = [
        Pattern(
            name="credit_card_generic",
            regex=r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b",
            score=0.9
        ),
    ]
    CONTEXT = ["carte", "card", "bancaire", "crédit", "paiement", "CB"]
    
    def __init__(self):
        super().__init__(
            supported_entity="CREDIT_CARD",
            patterns=self.PATTERNS,
            context=self.CONTEXT,
            supported_language="fr"
        )

# NIR
class NIRRecognizer(PatternRecognizer):
    PATTERNS = [
        Pattern(
            name="nir",
            regex=r"\b[12]\s?\d{2}\s?\d{2}\s?\d{2}\s?\d{3}\s?\d{3}\s?\d{2}\b",
            score=0.85
        )
    ]
    
    def __init__(self):
        super().__init__(
            supported_entity="FR_NIR",
            patterns=self.PATTERNS,
            context=["NIR", "sécurité sociale", "sécu"],
            supported_language="fr"
        )

# SIRET
class SIRETRecognizer(PatternRecognizer):
    PATTERNS = [
        Pattern(
            name="siret",
            regex=r"\b\d{3}\s?\d{3}\s?\d{3}\s?\d{5}\b",
            score=0.85
        )
    ]
    
    def __init__(self):
        super().__init__(
            supported_entity="FR_SIRET",
            patterns=self.PATTERNS,
            context=["SIRET", "entreprise"],
            supported_language="fr"
        )

# Téléphone français
class PhoneFRRecognizer(PatternRecognizer):
    PATTERNS = [
        Pattern(
            name="phone_fr",
            regex=r"\b0[1-9](?:[\s\.\-]?\d{2}){4}\b",
            score=0.9
        )
    ]
    
    def __init__(self):
        super().__init__(
            supported_entity="PHONE_NUMBER",
            patterns=self.PATTERNS,
            context=["tél", "téléphone", "phone", "mobile"],
            supported_language="fr"
        )

# IBAN français
class IBANFRRecognizer(PatternRecognizer):
    PATTERNS = [
        Pattern(
            name="iban_fr",
            regex=r"\bFR\d{2}[\s]?\d{4}[\s]?\d{4}[\s]?\d{4}[\s]?\d{4}[\s]?\d{4}[\s]?\d{3}\b",
            score=0.9
        )
    ]
    
    def __init__(self):
        super().__init__(
            supported_entity="IBAN_CODE",
            patterns=self.PATTERNS,
            context=["IBAN", "RIB", "compte bancaire"],
            supported_language="fr"
        )

# 4. Ajout de tes recognizers personnalisés (Assure-toi que les classes sont définies)
registry.add_recognizer(CreditCardRecognizerFR())
registry.add_recognizer(NIRRecognizer())
registry.add_recognizer(SIRETRecognizer())
registry.add_recognizer(PhoneFRRecognizer())
registry.add_recognizer(IBANFRRecognizer())

# 5. Création de l'Analyzer
analyzer = AnalyzerEngine(
    nlp_engine=nlp_engine, 
    registry=registry
)

anonymizer = AnonymizerEngine()

# Initialisation Groq
api_key_from_secrets = st.secrets["GROQ_API_KEY"]
groq_client = Groq(api_key=api_key_from_secrets)

# Stockage temporaire des sessions (en prod: Redis)
sessions: Dict[str, dict] = {}

class ProxyRequest(BaseModel):
    prompt: str
    model: str = "llama-3.3-70b-versatile"  # Modèle par défaut Groq
    temperature: float = 0.7
    max_tokens: int = 1024

class ProxyResponse(BaseModel):
    session_id: str
    original_prompt: str
    anonymized_prompt: str
    pii_detected: List[dict]
    llm_response: str
    final_response: str


def run_privacy_logic(prompt: str, model: str, temperature: float):
    session_id = str(uuid.uuid4())
    
    try:
        # 1. Analyse des PII (Utilisation du paramètre 'prompt' directement)
        analysis_results = analyzer.analyze(
            text=prompt,
            language='fr',
            entities=[
                "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", 
                "CREDIT_CARD", "IBAN_CODE", "IP_ADDRESS",
                "LOCATION", "DATE_TIME", "NRP"
            ]
        )
        
        # 2. Création des tokens
        operators = {}
        mapping = {}
        
        for i, result in enumerate(analysis_results):
            entity_type = result.entity_type
            original_text = prompt[result.start:result.end] # Corrigé ici
            token = f"<{entity_type}_{i}>"
            
            operators[result.entity_type] = OperatorConfig(
                "replace",
                {"new_value": token}
            )
            mapping[token] = original_text
        
        # 3. Anonymisation du texte
        anonymized_result = anonymizer.anonymize(
            text=prompt, # Corrigé ici
            analyzer_results=analysis_results,
            operators=operators
        )
        anonymized_text = anonymized_result.text
        
        # 4. Appel à Groq
        system_instruction = "Tu es un assistant utile. IMPORTANT : Ne modifie jamais les identifiants entre chevrons comme <PERSON_0>."
        
        chat_completion = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": anonymized_text}
            ],
            model=model, # Corrigé ici
            temperature=temperature, # Corrigé ici
            max_tokens=1024
        )

        llm_response = chat_completion.choices[0].message.content
        
        # 5. Désanonymisation
        final_response = llm_response
        for token, original_value in mapping.items():
            final_response = final_response.replace(token, original_value)
        
        # 6. Préparation des infos PII
        pii_info = [
            {
                "type": r.entity_type,
                "text": prompt[r.start:r.end], # Corrigé ici
                "score": round(r.score, 2),
                "start": r.start,
                "end": r.end
            }
            for r in analysis_results
        ]
        
        return {
            "original_prompt": prompt,
            "anonymized_prompt": anonymized_text,
            "pii_detected": pii_info,
            "final_response": final_response
        }

    except Exception as e:
        # On remonte l'erreur pour qu'elle soit affichée dans Streamlit
        raise Exception(f"Erreur interne : {str(e)}")

