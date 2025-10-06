"""
Article summarization for NewsFlow.

Provides extractive and abstractive summarization capabilities
for news articles using various NLP techniques.
"""

import logging
import re
from collections import Counter

import nltk
from sklearn.feature_extraction.text import TfidfVectorizer

logger = logging.getLogger(__name__)

# Ensure NLTK data is available
try:
    nltk.data.find("tokenizers/punkt")
except LookupError:
    try:
        nltk.download("punkt", quiet=True)
    except:
        pass

try:
    nltk.data.find("tokenizers/punkt_tab")
except LookupError:
    try:
        nltk.download("punkt_tab", quiet=True)
    except:
        pass

try:
    nltk.data.find("corpora/stopwords")
except LookupError:
    try:
        nltk.download("stopwords", quiet=True)
    except:
        pass


class ArticleSummarizer:
    """
    Article summarization using extractive and abstractive techniques.

    Provides multiple summarization methods including sentence ranking,
    keyword extraction, and optional transformer-based summarization.
    """

    def __init__(self, use_transformers: bool = False):
        """
        Initialize the summarizer.

        Args:
            use_transformers: Whether to use transformer models for abstractive summarization
        """
        self.use_transformers = use_transformers
        self.transformer_pipeline = None

        if use_transformers:
            self._init_transformer_model()

        # Initialize NLTK components
        try:
            self.stop_words = set(nltk.corpus.stopwords.words("english"))
        except:
            self.stop_words = set(
                [
                    "the",
                    "a",
                    "an",
                    "and",
                    "or",
                    "but",
                    "in",
                    "on",
                    "at",
                    "to",
                    "for",
                    "of",
                    "with",
                    "by",
                ],
            )

    def _init_transformer_model(self):
        """Initialize transformer model for abstractive summarization."""
        try:
            # Check for PyTorch first
            try:
                import torch

                logger.info(f"PyTorch {torch.__version__} is available")
            except ImportError:
                logger.warning("PyTorch not found. Install with: pip install torch")
                self.use_transformers = False
                return

            # Check for TensorFlow as alternative
            if not hasattr(self, "use_transformers") or not self.use_transformers:
                try:
                    import tensorflow as tf

                    logger.info(f"TensorFlow {tf.__version__} is available")
                    framework = "tf"
                except ImportError:
                    logger.warning("Neither PyTorch nor TensorFlow found")
                    self.use_transformers = False
                    return
            else:
                framework = "pt"

            from transformers import pipeline

            # Use a model with safetensors format for security
            model_name = "facebook/bart-large-cnn"  # This model supports safetensors

            logger.info(f"Loading summarization model: {model_name}")

            self.transformer_pipeline = pipeline(
                "summarization",
                model=model_name,
                framework=framework,
                device=-1,  # Use CPU
                truncation=True,
                clean_up_tokenization_spaces=True,
                # Note: safetensors is used automatically when available
            )
            logger.info("Transformer summarization model loaded successfully")

        except ImportError as e:
            logger.warning(f"Transformers library not available: {e}")
            self.use_transformers = False
        except Exception as e:
            logger.error(f"Error loading transformer model: {e}")
            logger.info("Falling back to extractive summarization")
            self.use_transformers = False

    def extractive_summary(self, text: str, num_sentences: int = 3) -> str:
        """
        Create extractive summary by selecting key sentences.

        Args:
            text: Text to summarize
            num_sentences: Number of sentences to include in summary

        Returns:
            Extractive summary as string
        """
        if not text or not text.strip():
            return ""

        try:
            # Tokenize into sentences
            sentences = nltk.sent_tokenize(text)

            if len(sentences) <= num_sentences:
                return text

            # Calculate sentence scores
            sentence_scores = self._calculate_sentence_scores(sentences, text)

            # Select top sentences
            top_sentences = sorted(
                sentence_scores.items(),
                key=lambda x: x[1],
                reverse=True,
            )[:num_sentences]

            # Sort by original order
            selected_indices = sorted([idx for idx, _ in top_sentences])
            summary_sentences = [sentences[idx] for idx in selected_indices]

            return " ".join(summary_sentences)

        except Exception as e:
            logger.error(f"Error in extractive summarization: {e}")
            # Fallback to first few sentences
            sentences = re.split(r"[.!?]+", text)
            return ". ".join(sentences[:num_sentences]) + "."

    def _calculate_sentence_scores(
        self,
        sentences: list[str],
        full_text: str,
    ) -> dict[int, float]:
        """
        Calculate importance scores for sentences.

        Args:
            sentences: List of sentences
            full_text: Complete text for context

        Returns:
            Dictionary mapping sentence index to importance score
        """
        scores = {}

        # Get word frequencies
        word_freq = self._get_word_frequencies(full_text)

        # Get TF-IDF scores
        tfidf_scores = self._get_tfidf_scores(sentences)

        for i, sentence in enumerate(sentences):
            score = 0.0

            # Clean sentence
            words = self._clean_sentence(sentence)

            if not words:
                scores[i] = 0.0
                continue

            # Word frequency score
            freq_score = sum(word_freq.get(word, 0) for word in words) / len(words)

            # TF-IDF score
            tfidf_score = tfidf_scores.get(i, 0)

            # Position score (earlier sentences get higher score)
            position_score = 1.0 - (i / len(sentences)) * 0.3

            # Length score (prefer medium-length sentences)
            length_score = min(len(words) / 20, 1.0) if len(words) < 40 else 0.5

            # Combine scores
            score = (
                freq_score * 0.4
                + tfidf_score * 0.3
                + position_score * 0.2
                + length_score * 0.1
            )

            scores[i] = score

        return scores

    def _get_word_frequencies(self, text: str) -> dict[str, float]:
        """Get normalized word frequencies."""
        words = self._clean_sentence(text)

        if not words:
            return {}

        word_count = Counter(words)
        max_freq = max(word_count.values())

        # Normalize frequencies
        return {word: count / max_freq for word, count in word_count.items()}

    def _get_tfidf_scores(self, sentences: list[str]) -> dict[int, float]:
        """Get TF-IDF scores for sentences."""
        try:
            if len(sentences) < 2:
                return {0: 1.0} if sentences else {}

            # Clean sentences
            cleaned_sentences = [
                " ".join(self._clean_sentence(sent)) for sent in sentences
            ]

            # Remove empty sentences
            valid_sentences = [
                (i, sent) for i, sent in enumerate(cleaned_sentences) if sent.strip()
            ]

            if len(valid_sentences) < 2:
                return {i: 1.0 for i, _ in valid_sentences}

            # Calculate TF-IDF
            vectorizer = TfidfVectorizer(
                max_features=1000,
                stop_words="english",
                lowercase=True,
            )

            tfidf_matrix = vectorizer.fit_transform(
                [sent for _, sent in valid_sentences],
            )

            # Calculate sentence scores as sum of TF-IDF values
            scores = {}
            for idx, (original_idx, _) in enumerate(valid_sentences):
                score = tfidf_matrix[idx].sum()
                scores[original_idx] = float(score)

            return scores

        except Exception as e:
            logger.warning(f"Error calculating TF-IDF scores: {e}")
            return dict.fromkeys(range(len(sentences)), 1.0)

    def _clean_sentence(self, sentence: str) -> list[str]:
        """Clean and tokenize a sentence."""
        # Remove punctuation and convert to lowercase
        cleaned = re.sub(r"[^\w\s]", "", sentence.lower())

        # Tokenize
        words = cleaned.split()

        # Remove stop words and short words
        return [word for word in words if word not in self.stop_words and len(word) > 2]

    def abstractive_summary(self, text: str, max_length: int = 150) -> str:
        """
        Create abstractive summary using transformer models.

        Args:
            text: Text to summarize
            max_length: Maximum length of summary

        Returns:
            Abstractive summary as string
        """
        if not self.use_transformers or not self.transformer_pipeline:
            logger.info("Transformers not available, using extractive summarization")
            return self.extractive_summary(text, num_sentences=3)

        if not text or not text.strip():
            return ""

        try:
            # Clean and prepare input text
            text = text.strip()

            # Truncate input text for transformer model (models typically handle 512-1024 tokens)
            max_input_length = 512  # Conservative for CPU inference
            if len(text) > max_input_length:
                # Try to truncate at sentence boundaries
                sentences = text[:max_input_length].split(". ")
                if len(sentences) > 1:
                    text = ". ".join(sentences[:-1]) + "."
                else:
                    text = text[:max_input_length]

            # Generate summary with optimized parameters for CPU
            result = self.transformer_pipeline(
                text,
                max_length=min(max_length, 150),  # Cap at 150 for performance
                min_length=max(20, max_length // 4),  # Ensure minimum quality
                do_sample=False,  # Deterministic for consistency
                truncation=True,
                clean_up_tokenization_spaces=True,
            )

            summary = result[0]["summary_text"].strip()

            # Ensure the summary ends with proper punctuation
            if summary and summary[-1] not in ".!?":
                summary += "."

            return summary

        except Exception as e:
            logger.error(f"Error in abstractive summarization: {e}")
            logger.info("Falling back to extractive summarization")
            # Fallback to extractive
            return self.extractive_summary(text, num_sentences=3)

    def get_keywords(self, text: str, top_n: int = 10) -> list[str]:
        """
        Extract important keywords using TF-IDF.

        Args:
            text: Text to extract keywords from
            top_n: Number of top keywords to return

        Returns:
            List of important keywords
        """
        if not text or not text.strip():
            return []

        try:
            # Clean text
            words = self._clean_sentence(text)

            if len(words) < 5:
                return words[:top_n]

            # Use TF-IDF for keyword extraction
            vectorizer = TfidfVectorizer(
                max_features=100,
                stop_words="english",
                lowercase=True,
                ngram_range=(1, 2),  # Include bigrams
            )

            # Prepare text for TF-IDF
            text_for_tfidf = " ".join(words)

            try:
                tfidf_matrix = vectorizer.fit_transform([text_for_tfidf])
                feature_names = vectorizer.get_feature_names_out()

                # Get scores
                scores = tfidf_matrix.toarray()[0]

                # Sort by score
                keyword_scores = [
                    (feature_names[i], scores[i]) for i in range(len(scores))
                ]
                keyword_scores.sort(key=lambda x: x[1], reverse=True)

                return [keyword for keyword, _ in keyword_scores[:top_n]]

            except ValueError:
                # Fallback to word frequency
                word_freq = Counter(words)
                return [word for word, _ in word_freq.most_common(top_n)]

        except Exception as e:
            logger.error(f"Error extracting keywords: {e}")
            # Simple fallback
            words = self._clean_sentence(text)
            word_freq = Counter(words)
            return [word for word, _ in word_freq.most_common(top_n)]

    def summarize_article(self, article, summary_type: str = "extractive") -> dict:
        """
        Comprehensive article summarization.

        Args:
            article: Article object to summarize
            summary_type: 'extractive' or 'abstractive'

        Returns:
            Dictionary with summary, keywords, and metadata
        """
        text = f"{article.title} {article.content}"

        if summary_type == "abstractive" and self.use_transformers:
            summary = self.abstractive_summary(text)
        else:
            summary = self.extractive_summary(text)

        keywords = self.get_keywords(article.content)

        return {
            "summary": summary,
            "keywords": keywords,
            "summary_type": summary_type,
            "original_length": len(article.content),
            "summary_length": len(summary),
            "compression_ratio": len(summary) / len(article.content)
            if article.content
            else 0,
        }

    def get_reading_level(self, text: str) -> dict:
        """
        Estimate reading level of text.

        Args:
            text: Text to analyze

        Returns:
            Dictionary with reading level metrics
        """
        if not text:
            return {"grade_level": 0, "difficulty": "unknown"}

        try:
            sentences = nltk.sent_tokenize(text)
            words = nltk.word_tokenize(text.lower())

            # Filter out punctuation
            words = [word for word in words if word.isalpha()]

            if not sentences or not words:
                return {"grade_level": 0, "difficulty": "unknown"}

            # Calculate Flesch Reading Ease (simplified)
            avg_sentence_length = len(words) / len(sentences)
            avg_syllables = sum(self._count_syllables(word) for word in words) / len(
                words,
            )

            # Simplified Flesch formula
            flesch_score = (
                206.835 - (1.015 * avg_sentence_length) - (84.6 * avg_syllables)
            )

            # Convert to grade level
            if flesch_score >= 90:
                grade_level = 5
                difficulty = "very_easy"
            elif flesch_score >= 80:
                grade_level = 6
                difficulty = "easy"
            elif flesch_score >= 70:
                grade_level = 7
                difficulty = "fairly_easy"
            elif flesch_score >= 60:
                grade_level = 8
                difficulty = "standard"
            elif flesch_score >= 50:
                grade_level = 10
                difficulty = "fairly_difficult"
            elif flesch_score >= 30:
                grade_level = 12
                difficulty = "difficult"
            else:
                grade_level = 16
                difficulty = "very_difficult"

            return {
                "flesch_score": flesch_score,
                "grade_level": grade_level,
                "difficulty": difficulty,
                "avg_sentence_length": avg_sentence_length,
                "avg_syllables": avg_syllables,
            }

        except Exception as e:
            logger.error(f"Error calculating reading level: {e}")
            return {"grade_level": 8, "difficulty": "standard"}

    def _count_syllables(self, word: str) -> int:
        """Count syllables in a word (simplified approach)."""
        word = word.lower()
        vowels = "aeiouy"
        count = 0
        prev_char_was_vowel = False

        for char in word:
            if char in vowels:
                if not prev_char_was_vowel:
                    count += 1
                prev_char_was_vowel = True
            else:
                prev_char_was_vowel = False

        # Handle silent 'e'
        if word.endswith("e"):
            count -= 1

        # Ensure at least 1 syllable
        return max(1, count)
