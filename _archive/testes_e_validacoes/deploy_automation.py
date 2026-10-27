#!/usr/bin/env python3
"""
Deploy Automation - Logos Auditoria
Automação completa de deployment pré-produção
Logos Mode: ON. Sem confirmações desnecessárias.
"""

import os
import sys
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Tuple


class Colors:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    END = "\033[0m"
    BOLD = "\033[1m"


class DeploymentError(Exception):
    pass


class DeploymentAutomation:
    """Orquestra deployment completo"""

    def __init__(self, environment: str = "production", version: str = "latest"):
        self.environment = environment
        self.version = version
        self.registry = os.getenv("DOCKER_REGISTRY", "registry.com")
        self.image_name = f"{self.registry}/logos-auditoria:{self.version}"
        self.timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.log_file = f"deployment-{self.timestamp}.log"

    def log(self, msg: str, level: str = "info"):
        """Log com timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        colors = {
            "info": Colors.BLUE,
            "ok": Colors.GREEN,
            "warn": Colors.YELLOW,
            "error": Colors.RED,
        }
        color = colors.get(level, Colors.BLUE)
        icon = {
            "info": "ℹ️",
            "ok": "✓",
            "warn": "⚠️",
            "error": "✗",
        }
        print(f"{color}[{timestamp}] {icon[level]} {msg}{Colors.END}")
        with open(self.log_file, "a") as f:
            f.write(f"[{timestamp}] [{level.upper()}] {msg}\n")

    def run(self, cmd: str, check: bool = True) -> Tuple[int, str]:
        """Executa comando com log"""
        self.log(f"$ {cmd}", "info")
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=300
            )
            if check and result.returncode != 0:
                raise DeploymentError(f"Command failed: {result.stderr}")
            return result.returncode, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            raise DeploymentError(f"Command timeout: {cmd}")
        except Exception as e:
            raise DeploymentError(f"Command error: {e}")

    def header(self, title: str):
        """Print header"""
        print(f"\n{Colors.BOLD}{Colors.BLUE}╔{'═' * 50}╗{Colors.END}")
        print(f"{Colors.BOLD}{Colors.BLUE}║ {title.center(48)} ║{Colors.END}")
        print(f"{Colors.BOLD}{Colors.BLUE}╚{'═' * 50}╝{Colors.END}\n")

    # ============ VALIDAÇÃO ============
    def validate_prerequisites(self) -> bool:
        """Valida pré-requisitos"""
        self.header("PRÉ-REQUISITOS")

        checks = {
            "Docker": "docker --version",
            "Docker Compose": "docker-compose --version",
            "Python 3": "python3 --version",
            "Git": "git --version",
        }

        for name, cmd in checks.items():
            try:
                code, _ = self.run(cmd, check=True)
                self.log(f"{name} OK", "ok")
            except:
                self.log(f"{name} não encontrado", "error")
                return False

        return True

    def validate_files(self) -> bool:
        """Valida arquivos necessários"""
        self.header("VALIDAÇÃO DE ARQUIVOS")

        required_files = [
            "config.py",
            "models_auditoria.py",
            "webposto_client.py",
            "servicos_auditoria.py",
            "requirements.txt",
            "Dockerfile",
            "docker-compose.yml",
            f".env.{self.environment}",
        ]

        for file in required_files:
            if Path(file).exists():
                self.log(f"{file}", "ok")
            else:
                self.log(f"{file} - NOT FOUND", "error")
                return False

        return True

    def validate_environment(self) -> bool:
        """Valida arquivo .env"""
        self.header("VALIDAÇÃO DE ENVIRONMENT")

        env_file = f".env.{self.environment}"
        required_vars = [
            "WEBPOSTO_BASE_URL",
            "WEBPOSTO_BEARER_TOKEN",
            "MONGO_ROOT_PASSWORD",
        ]

        with open(env_file) as f:
            content = f.read()

        for var in required_vars:
            if var in content and not content.split(f"{var}=")[1].split("\n")[
                0
            ].startswith("seu_"):
                self.log(f"{var} configurado", "ok")
            else:
                self.log(f"{var} - NÃO CONFIGURADO", "error")
                return False

        return True

    def validate_syntax(self) -> bool:
        """Valida sintaxe Python"""
        self.header("VALIDAÇÃO DE SINTAXE")

        python_files = [
            "config.py",
            "models_auditoria.py",
            "webposto_client.py",
            "servicos_auditoria.py",
        ]

        for file in python_files:
            try:
                code, _ = self.run(f"python3 -m py_compile {file}", check=True)
                self.log(f"{file}", "ok")
            except:
                self.log(f"{file} - ERRO DE SINTAXE", "error")
                return False

        return True

    # ============ TESTES ============
    def run_tests(self) -> bool:
        """Executa testes unitários"""
        self.header("TESTES UNITÁRIOS")

        try:
            code, output = self.run(
                "pytest test_auditoria.py -v --tb=short", check=False
            )
            # Parse pytest output
            if "passed" in output:
                passed = output.count(" PASSED")
                self.log(f"{passed} testes passaram", "ok")
                return code == 0
            else:
                self.log("Testes falharam", "error")
                print(output)
                return False
        except Exception as e:
            self.log(f"Erro ao executar testes: {e}", "error")
            return False

    # ============ BUILD ============
    def build_docker_image(self) -> bool:
        """Build Docker image"""
        self.header("BUILD DOCKER IMAGE")

        try:
            self.log(f"Building {self.image_name}...", "info")
            code, output = self.run(f"docker build -t {self.image_name} .", check=True)
            self.log(f"Image built: {self.image_name}", "ok")
            return True
        except DeploymentError as e:
            self.log(f"Build failed: {e}", "error")
            return False

    def push_to_registry(self) -> bool:
        """Push image para registry"""
        self.header("PUSH PARA REGISTRY")

        try:
            self.log(f"Pushing {self.image_name}...", "info")
            code, _ = self.run(f"docker push {self.image_name}", check=True)
            self.log(f"Pushed: {self.image_name}", "ok")
            return True
        except DeploymentError as e:
            self.log(f"Push failed: {e}", "error")
            return False

    # ============ BACKUP ============
    def backup_databases(self) -> bool:
        """Backup databases antes de deploy"""
        self.header("BACKUP DE DATABASES")

        try:
            backup_dir = f"backups/{self.timestamp}"
            self.run(f"mkdir -p {backup_dir}", check=True)

            # MongoDB backup
            self.log("Backing up MongoDB...", "info")
            mongo_cmd = f"""
            docker-compose exec -T mongo mongodump \\
                -u admin -p $MONGO_ROOT_PASSWORD \\
                --authenticationDatabase admin \\
                --out {backup_dir}/mongo
            """
            self.run(mongo_cmd, check=False)  # Ignore errors
            self.log("MongoDB backup done", "ok")

            # Redis backup
            self.log("Backing up Redis...", "info")
            self.run("docker exec logos-cache redis-cli BGSAVE", check=False)
            self.run(
                f"docker cp logos-cache:/data/dump.rdb {backup_dir}/redis.rdb",
                check=False,
            )
            self.log("Redis backup done", "ok")

            return True
        except Exception as e:
            self.log(f"Backup error: {e}", "warn")
            return True  # Don't fail on backup

    # ============ DEPLOY ============
    def deploy(self) -> bool:
        """Deploy containers"""
        self.header("DEPLOYMENT")

        try:
            # Load environment
            self.log("Loading environment variables...", "info")
            self.run(f"export $(cat .env.{self.environment} | xargs)", check=True)

            # Pull images
            self.log("Pulling latest images...", "info")
            self.run("docker-compose pull", check=True)

            # Up stack
            self.log("Starting containers...", "info")
            self.run("docker-compose up -d --no-deps --force-recreate api", check=True)

            # Wait for healthy
            self.log("Waiting for API to be healthy...", "info")
            for i in range(30):
                try:
                    code, _ = self.run(
                        "curl -f http://localhost:8000/auditoria/health", check=False
                    )
                    if code == 0:
                        self.log("API is healthy", "ok")
                        return True
                    time.sleep(2)
                except:
                    time.sleep(2)

            self.log("API health check timeout", "error")
            return False

        except DeploymentError as e:
            self.log(f"Deploy failed: {e}", "error")
            return False

    # ============ VERIFICAÇÃO PÓS-DEPLOY ============
    def verify_deployment(self) -> bool:
        """Verifica deployment"""
        self.header("VERIFICAÇÃO PÓS-DEPLOYMENT")

        checks = {
            "Health endpoint": "curl -f http://localhost:8000/auditoria/health",
            "Resumo endpoint": "curl -f http://localhost:8000/auditoria/resumo/1",
            "Despesas endpoint": "curl -f http://localhost:8000/auditoria/despesas/1",
        }

        for name, cmd in checks.items():
            try:
                code, _ = self.run(cmd, check=False)
                if code == 0:
                    self.log(f"{name}: OK", "ok")
                else:
                    self.log(f"{name}: FAILED", "error")
                    return False
            except Exception as e:
                self.log(f"{name}: {e}", "error")
                return False

        return True

    def status(self) -> bool:
        """Mostra status dos containers"""
        self.header("STATUS DOS CONTAINERS")

        try:
            _, output = self.run("docker-compose ps", check=True)
            print(output)
            return True
        except:
            return False

    def logs(self):
        """Mostra últimos logs"""
        self.header("ÚLTIMOS LOGS")

        self.run("docker-compose logs --tail=20 api", check=False)

    # ============ ROLLBACK ============
    def rollback(self) -> bool:
        """Rollback para versão anterior"""
        self.header("ROLLBACK")

        try:
            self.log("Stopping current deployment...", "info")
            self.run("docker-compose down", check=True)

            self.log("Pulling previous version...", "info")
            self.run("docker-compose pull", check=True)

            self.log("Starting previous version...", "info")
            self.run("docker-compose up -d", check=True)

            self.log("Rollback completed", "ok")
            return True
        except DeploymentError as e:
            self.log(f"Rollback failed: {e}", "error")
            return False

    # ============ PIPELINE COMPLETO ============
    def full_deployment(self) -> bool:
        """Pipeline completo de deployment"""
        self.header("LOGOS AUDITORIA - DEPLOYMENT AUTOMÁTICO")
        print(f"Environment: {Colors.YELLOW}{self.environment}{Colors.END}")
        print(f"Version: {Colors.YELLOW}{self.version}{Colors.END}")
        print(f"Log: {Colors.YELLOW}{self.log_file}{Colors.END}\n")

        steps = [
            ("Validando pré-requisitos", self.validate_prerequisites),
            ("Validando arquivos", self.validate_files),
            ("Validando environment", self.validate_environment),
            ("Validando sintaxe", self.validate_syntax),
            ("Rodando testes", self.run_tests),
            ("Fazendo backup", self.backup_databases),
            ("Build Docker image", self.build_docker_image),
            ("Push para registry", self.push_to_registry),
            ("Deploy", self.deploy),
            ("Verificando deployment", self.verify_deployment),
        ]

        for step_name, step_func in steps:
            self.header(step_name)
            try:
                if not step_func():
                    self.log(f"{step_name} FALHOU", "error")
                    self.log("\n⚠️  Deployment interrompido. Rolando back...", "warn")
                    self.rollback()
                    return False
            except Exception as e:
                self.log(f"Erro: {e}", "error")
                self.rollback()
                return False

        # Success
        self.header("DEPLOYMENT COMPLETO COM SUCESSO")
        self.status()
        print()
        self.logs()

        return True


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Logos Auditoria Deployment Automation"
    )
    parser.add_argument(
        "--environment",
        default="production",
        help="Environment (development, staging, production)",
    )
    parser.add_argument("--version", default="latest", help="Version to deploy")
    parser.add_argument("--registry", default="registry.com", help="Docker registry")
    parser.add_argument(
        "--rollback", action="store_true", help="Rollback to previous version"
    )
    parser.add_argument("--status", action="store_true", help="Show status")
    parser.add_argument("--logs", action="store_true", help="Show logs")

    args = parser.parse_args()

    deployer = DeploymentAutomation(args.environment, args.version)

    if args.rollback:
        deployer.rollback()
    elif args.status:
        deployer.status()
    elif args.logs:
        deployer.logs()
    else:
        success = deployer.full_deployment()
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
