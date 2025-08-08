#!/usr/bin/env python3
"""
GitHub Project Issues to CSV Exporter
Fetches issues from a GitHub organization project and exports to CSV format.
Uses GitHub CLI (gh) for authentication.
"""

import subprocess
import csv
import json
import sys

class GitHubProjectExporter:
    def __init__(self):
        """Initialize and verify GitHub CLI authentication."""
        self._verify_gh_auth()
    
    def _verify_gh_auth(self) -> None:
        """Verify GitHub CLI is available and authenticated."""
        try:
            subprocess.run(['gh', 'auth', 'status'], 
                          capture_output=True, text=True, check=True)
            print("Using GitHub CLI authentication")
        except FileNotFoundError:
            raise Exception(
                "GitHub CLI not found. Please install it:\n"
                "  macOS: brew install gh\n"
                "  Ubuntu/Debian: sudo apt install gh\n"
                "  Windows: winget install GitHub.cli"
            )
        except subprocess.CalledProcessError:
            raise Exception(
                "GitHub CLI not authenticated. Please run:\n"
                "  gh auth login"
            )
    
    def _make_graphql_request(self, query: str, variables: dict[str, any]) -> dict[str, any]:
        """Make GraphQL request using gh CLI."""
        payload = {
            "query": query,
            "variables": variables
        }
        
        try:
            result = subprocess.run([
                'gh', 'api', 'graphql', 
                '--input', '-'
            ], input=json.dumps(payload), text=True, capture_output=True, check=True)
            
            data = json.loads(result.stdout)
            
            if "errors" in data:
                raise Exception(f"GraphQL errors: {data['errors']}")
            
            return data["data"]
            
        except subprocess.CalledProcessError as e:
            raise Exception(f"gh CLI request failed: {e.stderr}")
        except json.JSONDecodeError as e:
            raise Exception(f"Failed to parse GraphQL response: {e}")
    
    def get_all_project_items(self, org: str, project_number: int) -> list[dict[str, any]]:
        """Fetch all project items, handling pagination."""
        all_items = []
        cursor = None
        
        while True:
            query = """
            query($org: String!, $number: Int!, $cursor: String) {
              organization(login: $org) {
                projectV2(number: $number) {
                  items(first: 100, after: $cursor) {
                    pageInfo {
                      hasNextPage
                      endCursor
                    }
                    nodes {
                      id
                      fieldValues(first: 20) {
                        nodes {
                          ... on ProjectV2ItemFieldTextValue {
                            text
                            field {
                              ... on ProjectV2FieldCommon {
                                name
                              }
                            }
                          }
                          ... on ProjectV2ItemFieldNumberValue {
                            number
                            field {
                              ... on ProjectV2FieldCommon {
                                name
                              }
                            }
                          }
                        }
                      }
                      content {
                        ... on Issue {
                          number
                          title
                          body
                          url
                          labels(first: 20) {
                            nodes {
                              name
                            }
                          }
                        }
                        ... on PullRequest {
                          number
                          title
                          body
                          url
                          labels(first: 20) {
                            nodes {
                              name
                            }
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
            """
            
            variables = {
                "org": org,
                "number": project_number,
                "cursor": cursor
            }
            
            data = self._make_graphql_request(query, variables)
            project_data = data["organization"]["projectV2"]["items"]
            
            all_items.extend(project_data["nodes"])
            
            if not project_data["pageInfo"]["hasNextPage"]:
                break
            
            cursor = project_data["pageInfo"]["endCursor"]
        
        return all_items
    
    def process_items_to_csv_rows(self, items: list[dict[str, any]]) -> list[list[str]]:
        """Convert project items to CSV rows."""
        csv_rows = []
        
        for item in items:
            content = item.get("content")
            if not content:  # Skip items without content (e.g., draft issues)
                continue
            
            # Extract basic issue/PR information
            number = content.get("number", "")
            title = content.get("title", "")
            body = content.get("body") or ""
            url = content.get("url", "")
            
            # Extract labels
            labels = []
            if content.get("labels", {}).get("nodes"):
                labels = [label["name"] for label in content["labels"]["nodes"]]
            
            # Determine type based on Epic label
            issue_type = "Epic" if "Epic" in labels else "Story"
            
            # Extract Story Points from project fields
            story_points = ""
            field_values = item.get("fieldValues", {}).get("nodes", [])
            for field_value in field_values:
                field_info = field_value.get("field", {})
                field_name = field_info.get("name", "")
                
                match field_name.lower():
                    case "story points":
                        if "number" in field_value:
                            story_points = str(field_value["number"])
                        elif "text" in field_value:
                            story_points = field_value["text"]
                        break
            
            # Format title with story points at the beginning if available
            formatted_title = f"[{story_points}] {title}" if story_points else title
            
            # Create CSV row: Type,Title,ReferenceId,Link,Description,AcceptanceCriteria
            csv_row = [
                issue_type,
                formatted_title,
                str(number),
                url,
                body.replace('\n', ' ').replace('\r', ' '),  # Clean up newlines
                ""  # AcceptanceCriteria (empty as requested)
            ]
            
            csv_rows.append(csv_row)
        
        return csv_rows
    
    def export_to_csv(self, org: str, project_number: int, output_file: str) -> None:
        """Main method to export project issues to CSV."""
        print(f"Fetching project data for {org}/projects/{project_number}...")
        
        # Get all project items
        items = self.get_all_project_items(org, project_number)
        print(f"Found {len(items)} items in the project")
        
        # Process items to CSV format
        csv_rows = self.process_items_to_csv_rows(items)
        print(f"Processed {len(csv_rows)} issues/PRs")
        
        # Write to CSV file (no header as requested)
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerows(csv_rows)
        
        print(f"Exported to {output_file}")

def main():
    # Configuration
    ORG = "conda"
    PROJECT_NUMBER = 22
    OUTPUT_FILE = "conda_project_issues.csv"
    
    try:
        exporter = GitHubProjectExporter()
        exporter.export_to_csv(ORG, PROJECT_NUMBER, OUTPUT_FILE)
        print("Export completed successfully!")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
