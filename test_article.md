# AWSでサーバレスアプリケーションを構築する

## はじめに

この記事では、lambdaとs3を使ったサーバレスアプリケーションの構築方法を解説します。

## 環境設定

AWSアカウントID: 123456789012

```bash
export AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
export AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
export AWS_SESSION_TOKEN=FwoGZXIvYXdzEBYaDHqa0AP1Rmsm3DXDYiLBAd5KGILAkOOabcdefghijklmnopqrstuvwxyz1234567890ABCDEFGHIJKLMNOPabcdefghijklmnopqrs
```

接続先: postgresql://admin:password123@192.168.1.100:5432/mydb

GitHubのトークン: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmn

api_key = "sk-1234567890abcdefghijklmnopqrstuvwxyz"

## アーキテクチャ

ユーザがブラウザからリクエストを送ると、API Gatewayを経由してlambda関数が実行されます。
データはdynamodbに保存され、静的ファイルはs3にホスティングされます。

Dockerコンテナをecs上で動かすこともできます。

ファイアーウォールの設定も忘れずに行いましょう。

## ディプロイ手順

terraformを使ってインフラをデプロイします。

password = "MySecretPass123!"

-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA0Z3VS5JJcds3xfn/ygWyF2PbnGMi
-----END RSA PRIVATE KEY-----
