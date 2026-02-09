variable "aws_region" {
  type        = string
  description = "AWS region for all resources."
  default     = "us-east-1"
}

variable "cluster_name" {
  type        = string
  description = "EKS cluster name."
  default     = "demo-eks"
}

variable "vpc_cidr" {
  type        = string
  description = "CIDR block for the VPC."
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidrs" {
  type        = list(string)
  description = "CIDR blocks for public subnets (2 required)."
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "node_instance_type" {
  type        = string
  description = "EC2 instance type for worker nodes."
  default     = "t3.small"
}

variable "node_desired_size" {
  type        = number
  description = "Desired node count."
  default     = 2
}

variable "node_min_size" {
  type        = number
  description = "Minimum node count."
  default     = 1
}

variable "node_max_size" {
  type        = number
  description = "Maximum node count."
  default     = 3
}

variable "website_image" {
  type        = string
  description = "Container image for the simple website."
  default     = "nginx:alpine"
}
