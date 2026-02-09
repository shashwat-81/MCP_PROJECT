output "cluster_name" {
  value       = aws_eks_cluster.main.name
  description = "EKS cluster name."
}

output "cluster_endpoint" {
  value       = aws_eks_cluster.main.endpoint
  description = "EKS API server endpoint."
}

output "cluster_ca_certificate" {
  value       = aws_eks_cluster.main.certificate_authority[0].data
  description = "Base64-encoded cluster CA certificate."
}

output "website_service_hostname" {
  value       = kubernetes_service.website.status[0].load_balancer[0].ingress[0].hostname
  description = "Public DNS name for the website load balancer (may be empty until ready)."
}
