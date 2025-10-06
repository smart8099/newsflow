import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class ScrapersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "newsflow.scrapers"
    verbose_name = "News Scrapers"

    def ready(self):
        """App initialization code that runs when Django starts."""
        # Download required NLTK data for text processing
        self.setup_nltk_data()

    def setup_nltk_data(self):
        """Download required NLTK datasets for article processing."""
        try:
            import os

            import nltk
            from django.conf import settings

            # Set up NLTK data directory for persistent storage
            nltk_data_path = os.path.join(settings.BASE_DIR, "nltk_data")
            os.makedirs(nltk_data_path, exist_ok=True)

            # Clear existing paths and set our custom path as the primary location
            # This ensures NLTK looks in our project directory first
            nltk.data.path.clear()
            nltk.data.path.append(nltk_data_path)

            # Only download in production or when explicitly enabled
            download_nltk = getattr(settings, "DOWNLOAD_NLTK_DATA", True)

            if download_nltk:
                logger.info("Checking NLTK data availability...")

                # Required datasets for newspaper4k and article processing
                required_datasets = [
                    "punkt",  # Tokenization
                    "stopwords",  # Stop words for keyword extraction
                    "averaged_perceptron_tagger",  # POS tagging
                    "wordnet",  # WordNet for semantic analysis
                ]

                # Improved dataset checking with correct paths
                dataset_paths = {
                    "punkt": "tokenizers/punkt",
                    "stopwords": "corpora/stopwords",
                    "averaged_perceptron_tagger": "taggers/averaged_perceptron_tagger",
                    "wordnet": "corpora/wordnet",
                }

                for dataset in required_datasets:
                    try:
                        # Check if dataset exists with correct path
                        nltk.data.find(dataset_paths[dataset])
                        logger.debug(f"NLTK dataset '{dataset}' already available")
                    except LookupError:
                        try:
                            logger.info(f"Downloading NLTK dataset: {dataset}")
                            # Download without quiet=True to ensure proper extraction
                            result = nltk.download(dataset, download_dir=nltk_data_path)
                            if result:
                                logger.info(
                                    f"Successfully downloaded NLTK dataset: {dataset}",
                                )
                            else:
                                logger.warning(
                                    f"NLTK download returned False for dataset: {dataset}",
                                )
                        except Exception as e:
                            logger.warning(
                                f"Failed to download NLTK dataset '{dataset}': {e}",
                            )
                            # Don't fail app startup if NLTK download fails
                            continue

                logger.info("NLTK data setup completed")

        except ImportError:
            logger.warning("NLTK not available, skipping data setup")
        except Exception as e:
            logger.error(f"Error setting up NLTK data: {e}")
            # Don't fail app startup

    @staticmethod
    def check_dependencies():
        """Check if all required dependencies are available."""
        missing_deps = []
        optional_deps = []

        # Required dependencies
        required = [
            ("newspaper4k", "newspaper"),
            ("lxml", "lxml"),
            ("requests", "requests"),
            ("feedparser", "feedparser"),
            ("beautifulsoup4", "bs4"),
        ]

        # Optional dependencies
        optional = [
            ("nltk", "nltk"),
            ("python-dateutil", "dateutil"),
            ("tldextract", "tldextract"),
        ]

        for package_name, import_name in required:
            try:
                __import__(import_name)
            except ImportError:
                missing_deps.append(package_name)

        for package_name, import_name in optional:
            try:
                __import__(import_name)
            except ImportError:
                optional_deps.append(package_name)

        if missing_deps:
            logger.error(f"Missing required dependencies: {', '.join(missing_deps)}")
            logger.error("Please install missing dependencies with: uv sync")

        if optional_deps:
            logger.warning(f"Missing optional dependencies: {', '.join(optional_deps)}")
            logger.warning("Some features may not work optimally")

        return len(missing_deps) == 0
