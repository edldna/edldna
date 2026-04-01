# Guia rapido para envio seguro ao GitHub

## 1) Garantir que segredos nao vao junto

- Nunca versione o arquivo `.env`.
- Use somente `.env.example` no repositório.
- Se alguma chave real foi exposta no passado, rotacione antes de publicar.

## 2) Verificar arquivos sensiveis ou pesados no stage

```bash
git status --short
git diff --name-only --cached
```

## 3) Remover do controle de versao (se estiver rastreado)

```bash
git rm --cached .env || true
git rm --cached -r alerts logs eval_buffer train_frames train_pipeline runs yt_frames yt_frames_done yt_dataset yt_dataset_merged models || true
git rm --cached frame.jpg train_urls.txt || true
```

## 4) Limpeza local opcional antes do push

```bash
rm -rf alerts/* logs/* eval_buffer/*
find . -type f \( -name "*.pt" -o -name "*.onnx" -o -name "*.jpg" \) -not -path "./alerts/.gitkeep" -delete
```

## 5) Revisao final do que sera publicado

```bash
git status --short
git diff --name-only
```

## 6) Commit e push

```bash
git add .
git commit -m "chore: preparar repositorio para publicacao segura"
git remote add origin <URL_DO_GITHUB>
git push -u origin main
```

## 7) Pos-publicacao recomendada

- Ative "Secret scanning" e "Dependabot alerts" no GitHub.
- Configure branch protection para `main`.
- Use GitHub Actions para lint/teste basico no PR.

