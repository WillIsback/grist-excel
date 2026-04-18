"""Model discovery module for dynamic model selection in vLLM."""
from typing import List, Optional
import requests
from config import Settings


def list_available_models(settings: Settings) -> List[str]:
    """Query vLLM /v1/models and return list of model IDs.
    
    Returns an empty list if vLLM is unreachable (graceful fallback).
    """
    try:
        response = requests.get(
            f"{settings.VLLM_BASE_URL}/v1/models",
            timeout=settings.VLLM_TIMEOUT
        )
        response.raise_for_status()
        data = response.json()
        return [m["id"] for m in data.get("data", [])]
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
        print(f"⚠️  Impossible de joindre vLLM ({settings.VLLM_BASE_URL}): {e}")
        print("   Utilisation du modèle par défaut.")
        return []
    except requests.exceptions.HTTPError as e:
        print(f"⚠️  Erreur HTTP depuis vLLM: {e}")
        return []
    except Exception as e:
        print(f"⚠️  Erreur inattendue lors de la découverte des modèles: {e}")
        return []


def select_model(
    settings: Settings,
    model_name: Optional[str] = None,
    interactive: bool = False
) -> str:
    """
    Resolve the model name to use.

    Priority:
    1. Explicit model_name argument
    2. Interactive selection from available models
    3. Default from Settings (fallback)
    """
    models = list_available_models(settings)

    if not models:
        print("⚠️  Aucun modèle disponible via vLLM, utilisation du défaut")
        return settings.VLLM_MODEL

    if model_name:
        if model_name in models:
            return model_name
        print(f"⚠️  Modèle '{model_name}' non trouvé. Modèles disponibles :")
        for i, m in enumerate(models, 1):
            print(f"   {i}. {m}")
        raise ValueError(f"Model '{model_name}' not available")

    if interactive:
        print("\nModèles disponibles via vLLM :")
        for i, m in enumerate(models, 1):
            print(f"  {i}. {m}")
        choice = input("\nChoisissez un modèle (numéro ou nom) : ").strip()
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(models):
                return models[idx]
        except ValueError:
            if choice in models:
                return choice
        raise ValueError(f"Choix invalide : {choice}")

    return models[0] if models else settings.VLLM_MODEL
